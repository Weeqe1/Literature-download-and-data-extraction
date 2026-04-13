"""增强的PDF下载模块，增加更多PDF来源和优化下载策略。

Provides functions for downloading OA PDFs from multiple sources.
Supports Unpaywall, PMC, Sci-Hub, ResearchGate, and author websites.
"""

import os
import re
import time
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, urljoin

import requests
import pandas as pd
from tqdm import tqdm

import logging
logger = logging.getLogger(__name__)

from .sources.base import sanitize_filename, doi_normalize, rate_limit_source

# ---------------------------------------------------------------------------
# PDF下载源配置
# ---------------------------------------------------------------------------
PDF_SOURCES = {
    'unpaywall': {
        'enabled': True,
        'priority': 1,
        'timeout': 30,
        'max_retries': 2,
    },
    'pmc': {
        'enabled': True,
        'priority': 2,
        'timeout': 30,
        'max_retries': 2,
    },
    'scihub': {
        'enabled': True,  # 仅用于学术研究
        'priority': 3,
        'timeout': 60,
        'max_retries': 3,
        'mirrors': [
            'https://sci-hub.se',
            'https://sci-hub.st',
            'https://sci-hub.ru',
        ]
    },
    'researchgate': {
        'enabled': True,
        'priority': 4,
        'timeout': 45,
        'max_retries': 2,
    },
    'arxiv': {
        'enabled': True,
        'priority': 5,
        'timeout': 30,
        'max_retries': 2,
    },
    'doi_redirect': {
        'enabled': True,
        'priority': 6,
        'timeout': 20,
        'max_retries': 1,
    }
}

# 下载失败原因诊断
FAIL_REASONS = {
    "no_url": "No downloadable PDF URL found",
    "http_403": "HTTP 403 Forbidden",
    "http_404": "HTTP 404 Not Found",
    "http_other": "HTTP error (non-200 status)",
    "too_small": "Downloaded file too small or not a valid PDF",
    "timeout": "Request timeout",
    "connection_error": "Connection error",
    "request_error": "Other request error",
    "disk_error": "File system error",
    "max_retries": "Maximum retry attempts exceeded",
    "source_disabled": "PDF source is disabled",
}

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def ensure_dir(path: str) -> None:
    """创建目录树（如果不存在）"""
    if path:
        os.makedirs(path, exist_ok=True)

def _cleanup_partial_file(out_path: str) -> None:
    """清理部分下载的文件"""
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except OSError:
        pass

def _check_disk_space(path: str, min_mb: int = 500) -> bool:
    """检查磁盘空间"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        free_mb = free / (1024 * 1024)
        return free_mb >= min_mb
    except OSError:
        return True

def validate_pdf_content(content: bytes) -> bool:
    """验证PDF内容有效性"""
    if len(content) < 100:
        return False
    if not content.startswith(b'%PDF'):
        return False
    # 检查PDF结尾标记
    if b'%%EOF' not in content[-1000:]:
        return False
    return True

def get_pdf_hash(content: bytes) -> str:
    """计算PDF内容哈希"""
    return hashlib.md5(content).hexdigest()

# ---------------------------------------------------------------------------
# Sci-Hub下载
# ---------------------------------------------------------------------------
def _get_scihub_mirrors() -> List[str]:
    """获取可用的Sci-Hub镜像"""
    return PDF_SOURCES['scihub']['mirrors']

def _try_scihub_download(doi: str, out_path: str, timeout: int = 60) -> Tuple[bool, str]:
    """尝试从Sci-Hub下载PDF"""
    if not PDF_SOURCES['scihub']['enabled']:
        return False, "source_disabled"
    
    mirrors = _get_scihub_mirrors()
    
    for mirror in mirrors:
        try:
            rate_limit_source('scihub')
            
            # 构建Sci-Hub URL
            scihub_url = f"{mirror}/{doi}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            
            # 获取Sci-Hub页面
            response = requests.get(scihub_url, headers=headers, timeout=timeout, allow_redirects=True)
            
            if response.status_code != 200:
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
                
                if validate_pdf_content(content):
                    with open(out_path, 'wb') as f:
                        f.write(content)
                    return True, "ok"
            
        except Exception as e:
            logger.debug(f"Sci-Hub download failed from {mirror}: {e}")
            continue
    
    return False, "scihub_failed"

# ---------------------------------------------------------------------------
# ResearchGate下载
# ---------------------------------------------------------------------------
def _try_researchgate_download(doi: str, out_path: str, timeout: int = 45) -> Tuple[bool, str]:
    """尝试从ResearchGate下载PDF"""
    if not PDF_SOURCES['researchgate']['enabled']:
        return False, "source_disabled"
    
    try:
        rate_limit_source('researchgate')
        
        # 构建ResearchGate搜索URL
        search_url = f"https://www.researchgate.net/search/publication?q={doi}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        response = requests.get(search_url, headers=headers, timeout=timeout)
        
        if response.status_code != 200:
            return False, "researchgate_failed"
        
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
            return False, "no_pdf_found"
        
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
            
            if validate_pdf_content(content):
                with open(out_path, 'wb') as f:
                    f.write(content)
                return True, "ok"
        
    except Exception as e:
        logger.debug(f"ResearchGate download failed: {e}")
    
    return False, "researchgate_failed"

# ---------------------------------------------------------------------------
# arXiv下载
# ---------------------------------------------------------------------------
def _try_arxiv_download(doi: str, out_path: str, timeout: int = 30) -> Tuple[bool, str]:
    """尝试从arXiv下载PDF"""
    if not PDF_SOURCES['arxiv']['enabled']:
        return False, "source_disabled"
    
    try:
        rate_limit_source('arxiv')
        
        # 从DOI中提取arXiv ID
        arxiv_id = None
        if 'arxiv' in doi.lower():
            # 提取arXiv ID
            match = re.search(r'(\d{4}\.\d{4,5})', doi)
            if match:
                arxiv_id = match.group(1)
        
        if not arxiv_id:
            return False, "not_arxiv"
        
        # 构建arXiv PDF URL
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/pdf,*/*',
        }
        
        response = requests.get(pdf_url, headers=headers, timeout=timeout, stream=True)
        
        if response.status_code == 200:
            content = b''
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk
            
            if validate_pdf_content(content):
                with open(out_path, 'wb') as f:
                    f.write(content)
                return True, "ok"
        
    except Exception as e:
        logger.debug(f"arXiv download failed: {e}")
    
    return False, "arxiv_failed"

# ---------------------------------------------------------------------------
# 增强的URL解析
# ---------------------------------------------------------------------------
def _resolve_pdf_url_enhanced(row: dict, doi: str, email: str) -> Tuple[Optional[str], bool, str]:
    """增强的PDF URL解析，按优先级尝试多个来源"""
    
    # 1. 检查现有URL（来自数据源：OpenAlex oa_url, Semantic Scholar openAccessPdf等）
    pdf_url = row.get("pdf_url")
    if pdf_url and pdf_url.startswith("http"):
        return pdf_url, True, "direct"
    
    # 2. 尝试Unpaywall
    if doi:
        from .sources.crossref import get_unpaywall_pdf_by_doi
        pdf_url, is_oa = get_unpaywall_pdf_by_doi(doi, email)
        if pdf_url and pdf_url.startswith("http"):
            return pdf_url, is_oa, "unpaywall"
    
    # 3. PMC回退
    if doi:
        from .downloader import _doi_to_pmcid, _get_pmc_pdf_url
        pmcid = _doi_to_pmcid(doi, email)
        if pmcid:
            pdf_url = _get_pmc_pdf_url(pmcid)
            if pdf_url:
                return pdf_url, True, "pmc"
    
    # 4. 尝试Sci-Hub（仅用于学术研究）
    if doi:
        pdf_url = f"https://sci-hub.se/{doi}"
        # 注意：这里只是返回URL，实际下载在download_file中处理
        return pdf_url, False, "scihub"
    
    # 5. 尝试ResearchGate
    if doi:
        pdf_url = f"https://www.researchgate.net/search/publication?q={doi}"
        return pdf_url, False, "researchgate"
    
    # 6. 尝试arXiv（如果DOI包含arXiv ID）
    if doi and 'arxiv' in doi.lower():
        match = re.search(r'(\d{4}\.\d{4,5})', doi)
        if match:
            arxiv_id = match.group(1)
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            return pdf_url, True, "arxiv"
    
    # 7. 尝试doi.org重定向作为最后手段
    if doi:
        doi_url = f"https://doi.org/{doi}"
        try:
            from .sources.base import rate_limit_source
            rate_limit_source('download')
            r = requests.head(doi_url, timeout=10, allow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and r.url and r.url != doi_url:
                # 一些出版商直接从DOI重定向提供PDF
                final_url = r.url
                if '/pdf' in final_url.lower() or final_url.endswith('.pdf'):
                    return final_url, True, "doi_redirect"
        except Exception:
            pass
    
    return None, False, "none"

# ---------------------------------------------------------------------------
# 增强的单篇下载
# ---------------------------------------------------------------------------
def _download_single_work_enhanced(args: Tuple) -> Dict[str, Any]:
    """增强的单篇文献下载，支持多个PDF来源"""
    from .harvester import LiteratureHarvester
    
    w, pdf_dir, email = args
    row = LiteratureHarvester.work_to_row(w)
    doi = doi_normalize(row.get("doi") or "")
    
    # 使用增强的URL解析
    pdf_url, is_oa, url_source = _resolve_pdf_url_enhanced(row, doi, email)
    row["is_oa"] = bool(is_oa)
    row["download_source"] = url_source
    
    if pdf_url:
        fn_title = sanitize_filename(
            f"{row.get('year')}_{row.get('journal')}_{row.get('title') or row.get('display_name') or 'paper'}.pdf"
        )
        out_file = os.path.join(pdf_dir, fn_title)
        
        # 根据来源选择下载方法
        if url_source == "scihub":
            ok, fail_reason = _try_scihub_download(doi, out_file)
        elif url_source == "researchgate":
            ok, fail_reason = _try_researchgate_download(doi, out_file)
        elif url_source == "arxiv":
            ok, fail_reason = _try_arxiv_download(doi, out_file)
        else:
            # 使用标准下载方法
            from .downloader import download_file
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
# 增强的主下载函数
# ---------------------------------------------------------------------------
def download_pdfs_enhanced(
    works: List[dict],
    out_dir: str,
    mailto: Optional[str] = None,
    email: Optional[str] = None,
    max_workers: int = 8,  # 默认使用8个线程
    checkpoint_interval: int = 50,  # 更频繁的检查点
    checkpoint_path: Optional[str] = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """增强的PDF下载函数，支持多个PDF来源和更好的性能"""
    import concurrent.futures
    
    ensure_dir(out_dir)
    pdf_dir = os.path.join(out_dir, "PDF")
    ensure_dir(pdf_dir)
    
    email_addr = email or mailto or "wangqi@ahut.edu.cn"
    
    if not checkpoint_path:
        checkpoint_path = os.path.join(out_dir, "_checkpoint.xlsx")
    
    cols = [
        "title", "abstract", "journal", "year", "doi", "authors",
        "affiliations", "cited_by_count", "open_access_status", "is_oa",
        "pdf_path", "source", "download_source", "download_status", "download_fail_detail",
    ]
    
    # 加载现有检查点以恢复
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
    
    # 下载统计
    download_stats = {
        'total': len(works_to_process),
        'success': 0,
        'failed': 0,
        'by_source': {},
        'by_reason': {},
    }
    
    if max_workers <= 1:
        # 顺序下载
        for i, args in enumerate(tqdm(download_args, desc="[Download] Sequential"), 1):
            row = _download_single_work_enhanced(args)
            rows.append(row)
            
            # 更新统计
            if row.get("pdf_path"):
                download_stats['success'] += 1
                source = row.get("download_source", "unknown")
                download_stats['by_source'][source] = download_stats['by_source'].get(source, 0) + 1
            else:
                download_stats['failed'] += 1
                reason = row.get("download_status", "unknown")
                download_stats['by_reason'][reason] = download_stats['by_reason'].get(reason, 0) + 1
            
            if i % checkpoint_interval == 0:
                if verbose:
                    logger.info("  [Checkpoint] Saving progress (%d/%d)...", i, len(download_args))
                _save_checkpoint_with_stats(rows, cols, checkpoint_path, download_stats)
            
            if i % 500 == 0:
                if not _check_disk_space(pdf_dir, min_mb=200):
                    logger.warning("  [Warning] Disk space critically low after %d downloads. Stopping.", i)
                    break
    else:
        # 并发下载
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_download_single_work_enhanced, args): i
                for i, args in enumerate(download_args)
            }
            
            with tqdm(total=len(download_args), desc=f"[Download] {max_workers} threads") as pbar:
                for future in concurrent.futures.as_completed(future_to_idx):
                    try:
                        row = future.result()
                        rows.append(row)
                        
                        # 更新统计
                        if row.get("pdf_path"):
                            download_stats['success'] += 1
                            source = row.get("download_source", "unknown")
                            download_stats['by_source'][source] = download_stats['by_source'].get(source, 0) + 1
                        else:
                            download_stats['failed'] += 1
                            reason = row.get("download_status", "unknown")
                            download_stats['by_reason'][reason] = download_stats['by_reason'].get(reason, 0) + 1
                        
                        completed += 1
                        pbar.update(1)
                        
                        if completed % checkpoint_interval == 0:
                            if verbose:
                                logger.info("  [Checkpoint] Saving progress (%d/%d)...", completed, len(download_args))
                            _save_checkpoint_with_stats(rows, cols, checkpoint_path, download_stats)
                            
                    except Exception as e:
                        logger.error("  [Download] Error in worker: %s", e)
                        download_stats['failed'] += 1
                        download_stats['by_reason']['exception'] = download_stats['by_reason'].get('exception', 0) + 1
    
    # 最终保存
    _save_checkpoint_with_stats(rows, cols, checkpoint_path, download_stats)
    
    # 保存下载报告
    _save_download_report(out_dir, download_stats)
    
    # 创建最终DataFrame
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    return df[cols]

def _save_checkpoint_with_stats(rows: List[Dict], cols: List[str], excel_path: str, stats: Dict) -> None:
    """保存检查点并记录统计信息"""
    try:
        df = pd.DataFrame(rows)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]
        df.to_excel(excel_path, index=False)
        
        # 保存统计信息
        stats_path = excel_path.replace('.xlsx', '_stats.json')
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
            
    except OSError as e:
        logger.warning("  [Checkpoint] Failed to save: %s", e)

def _save_download_report(out_dir: str, stats: Dict) -> None:
    """保存详细的下载报告"""
    report_path = os.path.join(out_dir, "download_report.txt")
    
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("PDF下载报告\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"总任务数: {stats['total']}\n")
            f.write(f"成功下载: {stats['success']}\n")
            f.write(f"下载失败: {stats['failed']}\n")
            f.write(f"成功率: {stats['success']/stats['total']*100:.1f}%\n\n")
            
            f.write("下载来源分布:\n")
            for source, count in sorted(stats['by_source'].items()):
                f.write(f"  {source}: {count}\n")
            
            f.write("\n失败原因分布:\n")
            for reason, count in sorted(stats['by_reason'].items()):
                f.write(f"  {reason}: {count}\n")
            
            f.write("\n建议:\n")
            if stats['success']/stats['total'] < 0.2:
                f.write("- 成功率较低，考虑调整搜索策略或使用更多PDF来源\n")
            if 'no_url' in stats['by_reason'] and stats['by_reason']['no_url'] > stats['total']*0.5:
                f.write("- 大量文献没有PDF链接，考虑限制为开放获取文献\n")
        
        logger.info("  [Report] Download diagnostic report saved to %s", report_path)
        
    except Exception as e:
        logger.warning("  [Report] Failed to save download report: %s", e)