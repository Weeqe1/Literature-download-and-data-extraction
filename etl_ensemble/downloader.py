"""PDF download module with concurrent downloading, checkpoint, and disk space monitoring.

Provides functions for downloading OA PDFs and assembling a final DataFrame.
Supports Unpaywall + PMC as download sources with detailed failure diagnostics.
Includes anti-ban protection with User-Agent rotation and smart delays.
"""

import os
import re
import time
import random
from typing import List, Dict, Any, Optional, Tuple

import requests
import pandas as pd
from tqdm import tqdm

import logging
logger = logging.getLogger(__name__)

from .sources.base import sanitize_filename, doi_normalize, rate_limit_source
from .anti_ban import get_anti_ban_manager, get_safe_headers, safe_request, wait_for_source

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_EMAIL = "wangqi@ahut.edu.cn"

# Download failure reasons for diagnostics
FAIL_REASONS = {
    "no_url": "No downloadable PDF URL found (not OA or Unpaywall miss)",
    "http_403": "HTTP 403 Forbidden (access denied after retries)",
    "http_404": "HTTP 404 Not Found",
    "http_other": "HTTP error (non-200 status)",
    "too_small": "Downloaded file too small or not a valid PDF (<100 bytes or HTML error page)",
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


def _download_from_scihub(doi: str, out_path: str, timeout: int = 60, max_retries: int = 3) -> Tuple[bool, str]:
    """Download PDF from Sci-Hub.
    
    Args:
        doi: DOI string.
        out_path: Output file path.
        timeout: Request timeout.
        max_retries: Maximum retry attempts.
        
    Returns:
        Tuple of (success: bool, fail_reason: str).
    """
    import re
    from urllib.parse import urljoin
    
    scihub_mirrors = [
        "https://sci-hub.se",
        "https://sci-hub.st", 
        "https://sci-hub.ru",
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    for mirror in scihub_mirrors:
        for attempt in range(1, max_retries + 1):
            try:
                rate_limit_source('scihub')
                
                # 构建Sci-Hub URL
                scihub_url = f"{mirror}/{doi}"
                
                # 获取Sci-Hub页面
                response = requests.get(scihub_url, headers=headers, timeout=timeout, allow_redirects=True)
                
                if response.status_code != 200:
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    continue
                
                # 从页面中提取PDF链接
                pdf_url_patterns = [
                    r'location\.href\s*=\s*["\']([^"\']+\.pdf)["\']',
                    r'iframe[^>]+src\s*=\s*["\']([^"\']+)["\']',
                    r'<a[^>]+href\s*=\s*["\']([^"\']+\.pdf)["\']',
                ]
                
                pdf_url = None
                for pattern in pdf_url_patterns:
                    match = re.search(pattern, response.text, re.IGNORECASE)
                    if match:
                        pdf_url = match.group(1)
                        break
                
                if not pdf_url:
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    continue
                
                # 确保URL完整
                if not pdf_url.startswith('http'):
                    pdf_url = urljoin(mirror, pdf_url)
                
                # 下载PDF
                pdf_response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
                
                if pdf_response.status_code == 200:
                    content = b''
                    for chunk in pdf_response.iter_content(chunk_size=8192):
                        if chunk:
                            content += chunk
                    
                    # 验证PDF内容
                    if len(content) > 100 and content.startswith(b'%PDF'):
                        with open(out_path, 'wb') as f:
                            f.write(content)
                        return True, "ok"
                
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
    
    return False, "scihub_failed"


def _download_from_researchgate(doi: str, title: str, out_path: str, timeout: int = 45, max_retries: int = 2) -> Tuple[bool, str]:
    """Download PDF from ResearchGate.
    
    Args:
        doi: DOI string.
        title: Paper title.
        out_path: Output file path.
        timeout: Request timeout.
        max_retries: Maximum retry attempts.
        
    Returns:
        Tuple of (success: bool, fail_reason: str).
    """
    import re
    from urllib.parse import urljoin, quote
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    for attempt in range(1, max_retries + 1):
        try:
            rate_limit_source('researchgate')
            
            # 构建ResearchGate搜索URL
            search_url = f"https://www.researchgate.net/search/publication?q={quote(doi)}"
            
            response = requests.get(search_url, headers=headers, timeout=timeout)
            
            if response.status_code != 200:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                continue
            
            # 从页面中提取PDF链接
            pdf_patterns = [
                r'href\s*=\s*["\']([^"\']+\.pdf)["\']',
                r'data-pdf-url\s*=\s*["\']([^"\']+)["\']',
                r'"pdf_url"\s*:\s*"([^"]+)"',
            ]
            
            pdf_url = None
            for pattern in pdf_patterns:
                match = re.search(pattern, response.text, re.IGNORECASE)
                if match:
                    pdf_url = match.group(1)
                    break
            
            if not pdf_url:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                continue
            
            # 确保URL完整
            if not pdf_url.startswith('http'):
                pdf_url = urljoin("https://www.researchgate.net", pdf_url)
            
            # 下载PDF
            pdf_response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
            
            if pdf_response.status_code == 200:
                content = b''
                for chunk in pdf_response.iter_content(chunk_size=8192):
                    if chunk:
                        content += chunk
                
                # 验证PDF内容
                if len(content) > 100 and content.startswith(b'%PDF'):
                    with open(out_path, 'wb') as f:
                        f.write(content)
                    return True, "ok"
            
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
    
    return False, "researchgate_failed"


def download_file(
    url: str,
    out_path: str,
    timeout: int = 60,
    max_retries: int = 3,
    verbose: bool = False,
    source: str = "standard",
    doi: str = None,
    title: str = None,
) -> Tuple[bool, str]:
    """Download a file from URL with retry logic and partial file cleanup.

    Args:
        url: URL to download.
        out_path: Local file path to save to.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retry attempts.
        verbose: Print retry messages.
        source: Download source type (standard, scihub, researchgate).
        doi: DOI string for special sources.
        title: Paper title for special sources.

    Returns:
        Tuple of (success: bool, fail_reason: str).
    """
    if not url:
        return False, "no_url"

    ensure_dir(os.path.dirname(out_path))
    
    # 处理特殊来源
    if source == "scihub" and doi:
        if verbose:
            logger.debug("  [Download] Trying Sci-Hub for %s", doi[:50])
        return _download_from_scihub(doi, out_path, timeout, max_retries)
    
    if source == "researchgate" and doi:
        if verbose:
            logger.debug("  [Download] Trying ResearchGate for %s", doi[:50])
        return _download_from_researchgate(doi, title or "", out_path, timeout, max_retries)

    # 标准下载逻辑 - 使用反封锁保护
    # 获取反封锁管理器
    anti_ban = get_anti_ban_manager()
    
    # 检查是否被封锁
    if anti_ban.is_source_banned(source):
        if verbose:
            logger.debug("  [Download] Source '%s' is banned, skipping", source)
        return False, "source_banned"

    for attempt in range(1, max_retries + 1):
        try:
            # 使用反封锁模块发送请求
            response = safe_request('GET', url, source=source, timeout=timeout, stream=True)
            
            if response is None:
                if verbose:
                    logger.debug("  [Download] Request blocked or failed (attempt %d/%d)", attempt, max_retries)
                if attempt < max_retries:
                    # 指数退避
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait_time)
                    continue
                return False, "request_blocked"
            
            # 检查响应状态
            if response.status_code == 404:
                if verbose:
                    logger.debug("  [Download] HTTP 404 for %s", url[:80])
                return False, "http_404"
            
            if response.status_code == 403:
                if verbose:
                    logger.debug("  [Download] HTTP 403 for %s (attempt %d/%d)", url[:80], attempt, max_retries)
                if attempt < max_retries:
                    wait_time = (3 * attempt) + random.uniform(0, 2)
                    time.sleep(wait_time)
                    continue
                return False, "http_403"
            
            if response.status_code != 200:
                if verbose:
                    logger.debug("  [Download] HTTP %d (attempt %d/%d)", response.status_code, attempt, max_retries)
                if attempt < max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait_time)
                    continue
                return False, "http_other"

            # 保存文件
            with open(out_path, "wb") as fh:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)

            # 检查文件大小
            file_size = os.path.getsize(out_path)
            if file_size < 100:
                if verbose:
                    logger.debug("  [Download] File too small (%d bytes), discarding", file_size)
                _cleanup_partial_file(out_path)
                if attempt < max_retries:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(wait_time)
                    continue
                return False, "too_small"

            # 检查是否为有效PDF
            try:
                with open(out_path, "rb") as fh:
                    header_bytes = fh.read(8)
                    if not header_bytes.startswith(b"%PDF"):
                        if verbose:
                            logger.debug("  [Download] Response is not a PDF (got HTML?), discarding")
                        _cleanup_partial_file(out_path)
                        if attempt < max_retries:
                            wait_time = (2 ** attempt) + random.uniform(0, 1)
                            time.sleep(wait_time)
                            continue
                        return False, "too_small"
            except Exception:
                pass

            # 成功
            return True, "ok"

        except requests.exceptions.ConnectionError as e:
            if verbose:
                logger.debug("  [Download] Connection error (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait_time)
                continue
            return False, "connection_error"

        except requests.exceptions.Timeout as e:
            if verbose:
                logger.debug("  [Download] Timeout (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait_time)
                continue
            return False, "timeout"

        except requests.exceptions.RequestException as e:
            if verbose:
                logger.debug("  [Download] Request error (attempt %d/%d): %s", attempt, max_retries, e)
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                wait_time = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait_time)
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
    1. Existing pdf_url from row (includes OpenAlex OA URL)
    2. Unpaywall API lookup (with full OA location scan)
    3. PMC fallback (DOI -> PMCID -> PDF)
    4. arXiv fallback (if DOI contains arXiv ID)
    5. DOI.org redirect as last resort
    6. Sci-Hub (for academic research)
    7. ResearchGate search

    Args:
        row: Work row dict.
        doi: Normalised DOI.
        email: Email for Unpaywall/NCBI.

    Returns:
        Tuple of (pdf_url, is_oa, source_name).
    """
    from .sources.crossref import get_unpaywall_pdf_by_doi

    # 1. Check existing URL (from source: OpenAlex oa_url, Semantic Scholar openAccessPdf, etc.)
    pdf_url = row.get("pdf_url")
    if pdf_url and pdf_url.startswith("http"):
        return pdf_url, True, "direct"

    # 2. Try Unpaywall
    if doi:
        pdf_url, is_oa = get_unpaywall_pdf_by_doi(doi, email)
        if pdf_url and pdf_url.startswith("http"):
            return pdf_url, is_oa, "unpaywall"

    # 3. PMC fallback
    if doi:
        pmcid = _doi_to_pmcid(doi, email)
        if pmcid:
            pdf_url = _get_pmc_pdf_url(pmcid)
            if pdf_url:
                return pdf_url, True, "pmc"

    # 4. arXiv fallback (if DOI contains arXiv ID)
    if doi and 'arxiv' in doi.lower():
        import re
        match = re.search(r'(\d{4}\.\d{4,5})', doi)
        if match:
            arxiv_id = match.group(1)
            arxiv_pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            return arxiv_pdf_url, True, "arxiv"

    # 5. Try doi.org redirect as last resort for OA articles
    if doi:
        doi_url = f"https://doi.org/{doi}"
        try:
            from .sources.base import rate_limit_source
            rate_limit_source('download')
            r = requests.head(doi_url, timeout=10, allow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.url and r.url != doi_url:
                # Some publishers serve PDF directly from the DOI redirect
                final_url = r.url
                if '/pdf' in final_url.lower() or final_url.endswith('.pdf'):
                    return final_url, True, "doi_redirect"
        except Exception:
            pass

    # 6. Try Sci-Hub (for academic research)
    if doi:
        scihub_url = f"https://sci-hub.se/{doi}"
        return scihub_url, False, "scihub"

    # 7. Try ResearchGate search
    if doi:
        title = row.get("title") or row.get("display_name") or ""
        if title:
            researchgate_url = f"https://www.researchgate.net/search/publication?q={doi}"
            return researchgate_url, False, "researchgate"

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
        
        # 根据来源选择下载方法
        title = row.get('title') or row.get('display_name') or ""
        ok, fail_reason = download_file(
            pdf_url, out_file, 
            max_retries=5,  # 增加重试次数
            verbose=False,
            source=url_source,
            doi=doi,
            title=title
        )
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
