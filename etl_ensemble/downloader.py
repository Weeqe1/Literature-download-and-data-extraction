"""PDF download module with concurrent downloading, checkpoint, and disk space monitoring.

Provides functions for downloading OA PDFs and assembling a final DataFrame.
Supports Unpaywall + PMC as download sources with detailed failure diagnostics.
"""

import os
import re
import time
from typing import List, Dict, Any, Optional, Tuple

import requests
import pandas as pd
from tqdm import tqdm

import logging
logger = logging.getLogger(__name__)

from .sources.base import sanitize_filename, doi_normalize, rate_limit_source

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_EMAIL = "wangqi@ahut.edu.cn"

# Download failure reasons for diagnostics
FAIL_REASONS = {
    "no_url": "No downloadable PDF URL found (not OA or Unpaywall miss)",
    "http_403": "HTTP 403 Forbidden (access denied)",
    "http_404": "HTTP 404 Not Found",
    "http_other": "HTTP error (non-200 status)",
    "too_small": "Downloaded file too small (<100 bytes, likely HTML error page)",
    "timeout": "Request timeout",
    "connection_error": "Connection error",
    "request_error": "Other request error",
    "disk_error": "File system error",
}


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
) -> Tuple[bool, str]:
    """Download a file from URL with retry logic and partial file cleanup.

    Args:
        url: URL to download.
        out_path: Local file path to save to.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        verbose: Print retry messages.

    Returns:
        Tuple of (success: bool, fail_reason: str).
    """
    if not url:
        return False, "no_url"

    ensure_dir(os.path.dirname(out_path))

    for attempt in range(1, max_retries + 1):
        try:
            rate_limit_source('crossref')
            with requests.get(url, stream=True, timeout=timeout) as r:
                if r.status_code == 404:
                    if verbose:
                        logger.debug("  [Download] HTTP 404 for %s", url[:80])
                    return False, "http_404"
                if r.status_code == 403:
                    if verbose:
                        logger.debug("  [Download] HTTP 403 for %s", url[:80])
                    return False, "http_403"
                if r.status_code != 200:
                    if verbose:
                        logger.debug("  [Download] HTTP %d (attempt %d/%d)", r.status_code, attempt, max_retries)
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return False, "http_other"

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
                    return False, "too_small"

                return True, "ok"

        except requests.exceptions.ConnectionError as e:
            if verbose:
                logger.debug("  [Download] Connection error (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False, "connection_error"

        except requests.exceptions.Timeout as e:
            if verbose:
                logger.debug("  [Download] Timeout (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False, "timeout"

        except requests.exceptions.RequestException as e:
            if verbose:
                logger.debug("  [Download] Request error (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            return False, "request_error"

        except OSError as e:
            if verbose:
                logger.debug("  [Download] File system error: %s", e)
            _cleanup_partial_file(out_path)
            return False, "disk_error"

    _cleanup_partial_file(out_path)
    return False, "max_retries"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------
PMC_ID_CONV_API = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
PMC_PDF_BASE = "https://www.ncbi.nlm.nih.gov/pmc/articles"


def _doi_to_pmcid(doi: str, email: str) -> Optional[str]:
    """Convert DOI to PMC ID using NCBI ID Converter API.

    Args:
        doi: DOI string.
        email: Contact email for NCBI.

    Returns:
        PMC ID (e.g., 'PMC7612345') or None.
    """
    if not doi:
        return None
    try:
        params = {
            "ids": doi,
            "format": "json",
            "email": email,
        }
        rate_limit_source('crossref')
        r = requests.get(PMC_ID_CONV_API, params=params, timeout=15)
        if r.status_code != 200:
            return None
        js = r.json()
        records = js.get("records", [])
        for rec in records:
            pmcid = rec.get("pmcid")
            if pmcid:
                return pmcid
    except Exception:
        pass
    return None


def _get_pmc_pdf_url(pmcid: str) -> Optional[str]:
    """Get PDF download URL for a PMC article.

    Args:
        pmcid: PMC ID (e.g., 'PMC7612345').

    Returns:
        PDF URL or None.
    """
    if not pmcid:
        return None
    # PMC PDF URL pattern
    return f"{PMC_PDF_BASE}/{pmcid}/pdf/"


def _resolve_pdf_url(row: dict, doi: str, email: str) -> Tuple[Optional[str], bool, str]:
    """Try to find a downloadable PDF URL for a work.

    Resolution order:
    1. Existing pdf_url from row
    2. Unpaywall API lookup
    3. PMC fallback (DOI -> PMCID -> PDF)

    Args:
        row: Work row dict.
        doi: Normalised DOI.
        email: Email for Unpaywall/NCBI.

    Returns:
        Tuple of (pdf_url, is_oa, source_name).
    """
    from .sources.crossref import get_unpaywall_pdf_by_doi

    # 1. Check existing URL
    pdf_url = row.get("pdf_url")
    if pdf_url:
        return pdf_url, True, "direct"

    # 2. Try Unpaywall
    if doi:
        pdf_url, is_oa = get_unpaywall_pdf_by_doi(doi, email)
        if pdf_url:
            return pdf_url, is_oa, "unpaywall"

    # 3. PMC fallback
    if doi:
        pmcid = _doi_to_pmcid(doi, email)
        if pmcid:
            pdf_url = _get_pmc_pdf_url(pmcid)
            if pdf_url:
                return pdf_url, True, "pmc"

    return None, False, "none"


# ---------------------------------------------------------------------------
# Single-work download (for thread pool)
# ---------------------------------------------------------------------------
def _download_single_work(args: Tuple) -> Dict[str, Any]:
    """Download a single work's PDF. Designed for use with ThreadPoolExecutor.

    Args:
        args: Tuple of (work_dict, pdf_dir, email).

    Returns:
        Normalised row dict with pdf_path, is_oa, download_source, download_status set.
    """
    from .harvester import LiteratureHarvester

    w, pdf_dir, email = args
    row = LiteratureHarvester.work_to_row(w)
    doi = doi_normalize(row.get("doi") or "")

    pdf_url, is_oa, url_source = _resolve_pdf_url(row, doi, email)
    row["is_oa"] = bool(is_oa)
    row["download_source"] = url_source

    if pdf_url:
        fn_title = sanitize_filename(
            f"{row.get('year')}_{row.get('journal')}_{row.get('title') or row.get('display_name') or 'paper'}.pdf"
        )
        out_file = os.path.join(pdf_dir, fn_title)
        ok, fail_reason = download_file(pdf_url, out_file, max_retries=3, verbose=False)
        row["pdf_path"] = out_file if ok else None
        row["download_status"] = "ok" if ok else fail_reason
        if not ok:
            row["download_fail_detail"] = FAIL_REASONS.get(fail_reason, fail_reason)
    else:
        row["pdf_path"] = None
        row["download_status"] = "no_url"
        row["download_fail_detail"] = FAIL_REASONS["no_url"]

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
        "pdf_path", "source", "download_source", "download_status", "download_fail_detail",
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

    # Generate download diagnostic report
    _generate_download_report(df, out_dir, verbose)

    return df


def _generate_download_report(df: pd.DataFrame, out_dir: str, verbose: bool = True) -> None:
    """Generate a download diagnostic report.

    Args:
        df: DataFrame with download results.
        out_dir: Output directory.
        verbose: Print summary to log.
    """
    report_path = os.path.join(out_dir, "download_report.txt")

    total = len(df)
    if total == 0:
        return

    succeeded = df["pdf_path"].notna().sum()
    failed = total - succeeded

    # Count by download source
    source_counts = df["download_source"].value_counts().to_dict() if "download_source" in df.columns else {}

    # Count by failure reason
    fail_reasons = {}
    if "download_status" in df.columns:
        failed_df = df[df["pdf_path"].isna()]
        fail_reasons = failed_df["download_status"].value_counts().to_dict()

    # OA statistics
    oa_count = df["is_oa"].fillna(False).sum() if "is_oa" in df.columns else 0

    report_lines = [
        "=" * 60,
        "PDF Download Diagnostic Report",
        "=" * 60,
        f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Summary:",
        f"  Total works:       {total}",
        f"  PDFs downloaded:   {succeeded} ({succeeded/total*100:.1f}%)",
        f"  Failed:            {failed} ({failed/total*100:.1f}%)",
        f"  Open Access (OA):  {int(oa_count)} ({oa_count/total*100:.1f}%)",
        "",
        "Download Sources:",
    ]

    for src, cnt in sorted(source_counts.items(), key=lambda x: -x[1]):
        report_lines.append(f"  {src:20s} {cnt:5d} ({cnt/total*100:.1f}%)")

    report_lines.append("")
    report_lines.append("Failure Reasons (for failed downloads):")

    for reason, cnt in sorted(fail_reasons.items(), key=lambda x: -x[1]):
        detail = FAIL_REASONS.get(reason, reason)
        report_lines.append(f"  {reason:20s} {cnt:5d} - {detail}")

    # Sample failures for debugging
    if "download_fail_detail" in df.columns and failed > 0:
        report_lines.append("")
        report_lines.append("Sample Failed Downloads (up to 20):")
        report_lines.append("-" * 60)
        failed_samples = df[df["pdf_path"].isna()].head(20)
        for _, row in failed_samples.iterrows():
            title = str(row.get("title", ""))[:60]
            doi = str(row.get("doi", ""))
            status = str(row.get("download_status", ""))
            detail = str(row.get("download_fail_detail", ""))
            report_lines.append(f"  Title: {title}")
            report_lines.append(f"  DOI:   {doi}")
            report_lines.append(f"  Status: {status} - {detail}")
            report_lines.append("")

    report_text = "\n".join(report_lines)

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        if verbose:
            logger.info("  [Report] Download diagnostic report saved to %s", report_path)
    except Exception as e:
        logger.warning("  [Report] Failed to save report: %s", e)

    if verbose:
        logger.info("  [Stats] Download: %d/%d succeeded (%.1f%%), Sources: %s",
                     succeeded, total, succeeded/total*100 if total > 0 else 0,
                     ", ".join(f"{k}={v}" for k, v in source_counts.items()))
