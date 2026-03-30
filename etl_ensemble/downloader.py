"""PDF download module with concurrent downloading, checkpoint, and disk space monitoring.

Provides functions for downloading OA PDFs and assembling a final DataFrame.
"""

import os
import time
from typing import List, Dict, Any, Optional, Tuple

import requests
import pandas as pd
from tqdm import tqdm

import logging
logger = logging.getLogger(__name__)

from .sources.base import sanitize_filename, doi_normalize, rate_limit

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_EMAIL = "wangqi@ahut.edu.cn"


def ensure_dir(path: str) -> None:
    """Create directory tree if it doesn't exist.

    Args:
        path: Directory path.
    """
    if path:
        os.makedirs(path, exist_ok=True)


# ---------------------------------------------------------------------------
# Low-level download helpers
# ---------------------------------------------------------------------------
def _cleanup_partial_file(out_path: str) -> None:
    """Remove a partially downloaded file if it exists.

    Args:
        out_path: Path to file to remove.
    """
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except OSError:
        pass


def _check_disk_space(path: str, min_mb: int = 500) -> bool:
    """Check if there's enough disk space at the given path.

    Args:
        path: Directory to check.
        min_mb: Minimum free megabytes required.

    Returns:
        True if sufficient space is available.
    """
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        free_mb = free / (1024 * 1024)
        return free_mb >= min_mb
    except OSError:
        return True


def download_file(
    url: str,
    out_path: str,
    timeout: int = 60,
    max_retries: int = 3,
    verbose: bool = False,
) -> bool:
    """Download a file from URL with retry logic and partial file cleanup.

    Args:
        url: URL to download.
        out_path: Local file path to save to.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        verbose: Print retry messages.

    Returns:
        True if download succeeded, False otherwise.
    """
    if not url:
        return False

    ensure_dir(os.path.dirname(out_path))

    for attempt in range(1, max_retries + 1):
        try:
            rate_limit()
            with requests.get(url, stream=True, timeout=timeout) as r:
                if r.status_code == 404 or r.status_code == 403:
                    if verbose:
                        logger.debug("  [Download] HTTP %d for %s...", r.status_code, url[:80])
                    return False
                if r.status_code != 200:
                    if verbose:
                        logger.debug("  [Download] HTTP %d (attempt %d/%d)", r.status_code, attempt, max_retries)
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return False

                with open(out_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)

                if os.path.getsize(out_path) < 100:
                    if verbose:
                        logger.debug("  [Download] File too small (%d bytes), discarding", os.path.getsize(out_path))
                    _cleanup_partial_file(out_path)
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return False

                return True

        except requests.exceptions.ConnectionError as e:
            if verbose:
                logger.debug("  [Download] Connection error (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue

        except requests.exceptions.Timeout as e:
            if verbose:
                logger.debug("  [Download] Timeout (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue

        except requests.exceptions.RequestException as e:
            if verbose:
                logger.debug("  [Download] Request error (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue

        except OSError as e:
            if verbose:
                logger.debug("  [Download] File system error: %s", e)
            _cleanup_partial_file(out_path)
            return False

    _cleanup_partial_file(out_path)
    return False


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------
def _resolve_pdf_url(row: dict, doi: str, email: str) -> Tuple[Optional[str], bool]:
    """Try to find a downloadable PDF URL for a work.

    Args:
        row: Work row dict.
        doi: Normalised DOI.
        email: Email for Unpaywall.

    Returns:
        Tuple of (pdf_url, is_oa).
    """
    from .sources.crossref import get_unpaywall_pdf_by_doi

    pdf_url = row.get("pdf_url")
    is_oa = False
    if pdf_url:
        is_oa = True
        return pdf_url, is_oa
    if doi:
        pdf_url, is_oa = get_unpaywall_pdf_by_doi(doi, email)
    return pdf_url, is_oa


# ---------------------------------------------------------------------------
# Single-work download (for thread pool)
# ---------------------------------------------------------------------------
def _download_single_work(args: Tuple) -> Dict[str, Any]:
    """Download a single work's PDF. Designed for use with ThreadPoolExecutor.

    Args:
        args: Tuple of (work_dict, pdf_dir, email).

    Returns:
        Normalised row dict with pdf_path set on success.
    """
    from .harvester import LiteratureHarvester

    w, pdf_dir, email = args
    row = LiteratureHarvester.work_to_row(w)
    doi = doi_normalize(row.get("doi") or "")

    pdf_url, is_oa = _resolve_pdf_url(row, doi, email)
    row["is_oa"] = bool(is_oa)

    if pdf_url:
        fn_title = sanitize_filename(
            f"{row.get('year')}_{row.get('journal')}_{row.get('title') or row.get('display_name') or 'paper'}.pdf"
        )
        out_file = os.path.join(pdf_dir, fn_title)
        ok = download_file(pdf_url, out_file, max_retries=3, verbose=False)
        row["pdf_path"] = out_file if ok else None
    else:
        row["pdf_path"] = None

    return row


# ---------------------------------------------------------------------------
# Checkpoint save
# ---------------------------------------------------------------------------
def _save_checkpoint(rows: List[Dict], cols: List[str], excel_path: str) -> None:
    """Save current progress as a checkpoint Excel file.

    Args:
        rows: List of row dicts.
        cols: Column order for DataFrame.
        excel_path: Output Excel path.
    """
    try:
        df = pd.DataFrame(rows)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]
        df.to_excel(excel_path, index=False)
    except OSError as e:
        logger.warning("  [Checkpoint] Failed to save: %s", e)


# ---------------------------------------------------------------------------
# Main download orchestration
# ---------------------------------------------------------------------------
def download_pdfs_and_assemble(
    works: List[dict],
    out_dir: str,
    mailto: Optional[str] = None,
    email: Optional[str] = None,
    max_workers: int = 4,
    checkpoint_interval: int = 100,
    checkpoint_path: Optional[str] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Download OA PDFs and assemble final DataFrame.

    Features:
    - Concurrent downloading with ThreadPoolExecutor
    - Periodic checkpoint saves to Excel
    - Disk space monitoring
    - Retry with exponential backoff on download failures

    Args:
        works: List of work dicts to process.
        out_dir: Output directory for Excel and PDFs.
        mailto: Email for Unpaywall/Crossref polite requests.
        email: Email for Unpaywall.
        max_workers: Number of concurrent download threads (1 = sequential).
        checkpoint_interval: Save checkpoint every N downloads.
        checkpoint_path: Path for checkpoint Excel.
        verbose: Print progress messages.

    Returns:
        DataFrame with all downloaded works.
    """
    import concurrent.futures

    ensure_dir(out_dir)
    pdf_dir = os.path.join(out_dir, "PDF")
    ensure_dir(pdf_dir)

    email_addr = email or mailto or DEFAULT_EMAIL

    if not checkpoint_path:
        checkpoint_path = os.path.join(out_dir, "_checkpoint.xlsx")

    cols = [
        "title", "abstract", "journal", "year", "doi", "authors",
        "affiliations", "cited_by_count", "open_access_status", "is_oa",
        "pdf_path", "source",
    ]

    # Load existing checkpoint to resume
    existing_dois: Dict[str, bool] = {}
    if os.path.exists(checkpoint_path):
        try:
            df_ckpt = pd.read_excel(checkpoint_path)
            for _, row in df_ckpt.iterrows():
                d = doi_normalize(str(row.get("doi", "")) if pd.notna(row.get("doi")) else "")
                if d:
                    existing_dois[d] = True
            if verbose:
                logger.info("  [Resume] Loaded %d DOIs from checkpoint", len(existing_dois))
        except Exception:
            pass

    works_to_process = [w for w in works if not (doi_normalize(w.get("doi") or "") and doi_normalize(w.get("doi") or "") in existing_dois)]

    if verbose:
        logger.info("  [Download] %d works to process (of %d total)", len(works_to_process), len(works))

    if not works_to_process:
        if os.path.exists(checkpoint_path):
            df = pd.read_excel(checkpoint_path)
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            return df[cols]
        return pd.DataFrame(columns=cols)

    if not _check_disk_space(pdf_dir, min_mb=500):
        logger.warning("  [Warning] Low disk space (<500MB free). Downloads may fail.")

    rows: List[Dict[str, Any]] = []
    download_args = [(w, pdf_dir, email_addr) for w in works_to_process]

    if max_workers <= 1:
        for i, args in enumerate(tqdm(download_args, desc="[Download] Sequential"), 1):
            row = _download_single_work(args)
            rows.append(row)
            if i % checkpoint_interval == 0:
                if verbose:
                    logger.info("  [Checkpoint] Saving progress (%d/%d)...", i, len(download_args))
                _save_checkpoint(rows, cols, checkpoint_path)
            if i % 500 == 0:
                if not _check_disk_space(pdf_dir, min_mb=200):
                    logger.warning("  [Warning] Disk space critically low after %d downloads. Stopping.", i)
                    break
    else:
        completed = 0
        failed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_download_single_work, args): i
                for i, args in enumerate(download_args)
            }
            with tqdm(total=len(download_args), desc=f"[Download] {max_workers} threads") as pbar:
                for future in concurrent.futures.as_completed(future_to_idx):
                    try:
                        row = future.result()
                        rows.append(row)
                        if row.get("pdf_path"):
                            completed += 1
                        else:
                            failed += 1
                    except Exception as e:
                        failed += 1
                        if verbose and failed <= 5:
                            logger.warning("  [Download] Worker error: %s", e)

                    pbar.update(1)
                    total_done = completed + failed
                    if total_done % checkpoint_interval == 0 and total_done > 0:
                        _save_checkpoint(rows, cols, checkpoint_path)
                        if verbose:
                            pbar.set_postfix(ok=completed, fail=failed)
                    if total_done % 500 == 0:
                        if not _check_disk_space(pdf_dir, min_mb=200):
                            logger.warning("  [Warning] Disk space critically low. Cancelling remaining downloads.")
                            for f in future_to_idx:
                                f.cancel()
                            break

        if verbose:
            logger.info("  [Download] Complete: %d succeeded, %d failed", completed, failed)

    _save_checkpoint(rows, cols, checkpoint_path)

    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]
    return df
