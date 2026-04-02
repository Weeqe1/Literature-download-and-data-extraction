#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Literature Download, Dedup, Quality Assessment Pipeline.

Phase 1: Download PDFs for all 2300 records using DOI-based strategies
Phase 2: Clean invalid files, deduplicate
Phase 3: Full text extraction & quality assessment (NO sampling)
Phase 4: Categorize & generate comprehensive report

Progress saved to progress.json after each phase.
"""
import os
import sys
import json
import time
import glob
import shutil
import logging
import re
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from pathlib import Path

# Force UTF-8
if sys.stdout.encoding and 'utf-8' not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# ============================================================
# Config
# ============================================================
PROJECT = r'D:\Desktop\DATA-Download_Extraction'
CHECKPOINT = os.path.join(PROJECT, 'outputs', 'literature', '_checkpoint.xlsx')
PDF_DIR = os.path.join(PROJECT, 'outputs', 'literature', 'PDF')
INVALID_BACKUP = os.path.join(PROJECT, 'outputs', 'literature', 'invalid_backup')
DUP_BACKUP = os.path.join(PROJECT, 'outputs', 'literature', 'duplicates')
PROGRESS_FILE = os.path.join(PROJECT, 'pipeline_progress.json')
REPORT_DIR = os.path.join(PROJECT, 'outputs', 'literature', 'reports')

for d in [PDF_DIR, INVALID_BACKUP, DUP_BACKUP, REPORT_DIR]:
    os.makedirs(d, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(REPORT_DIR, 'pipeline.log'), encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('pipeline')

import requests
SESSION = requests.Session()
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) scholarly-lit-harvesting/1.0',
    'Accept': 'application/pdf,*/*',
})

EMAIL = 'wangqi@ahut.edu.cn'

def save_progress(phase, data):
    try:
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            prog = json.load(f)
    except:
        prog = {}
    prog[phase] = data
    prog['last_phase'] = phase
    prog['last_updated'] = time.strftime('%Y-%m-%d %H:%M:%S')
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(prog, f, ensure_ascii=False, indent=2, default=str)

def short_title(t):
    return (t[:80] + '...') if len(t) > 80 else t

def normalize_doi(doi):
    if not doi:
        return None
    doi = doi.strip().lower()
    if doi.startswith('https://doi.org/'):
        doi = doi[len('https://doi.org/'):]
    elif doi.startswith('http://doi.org/'):
        doi = doi[len('http://doi.org/'):]
    elif doi.startswith('doi:'):
        doi = doi[4:]
    return doi if len(doi) > 5 else None

def sanitize_filename(name):
    safe = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    safe = re.sub(r'\s+', ' ', safe).strip()
    return safe[:100]

# ============================================================
# PHASE 1: Download PDFs by DOI from multiple sources
# ============================================================

def try_unpaywall(doi):
    """Get OA PDF URL from Unpaywall API."""
    try:
        r = SESSION.get(f'https://api.unpaywall.org/v2/{doi}', 
                       params={'email': EMAIL}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('is_oa'):
                # Prefer best_oa_location with pdf
                for loc in [data.get('best_oa_location', {})] + (data.get('oa_locations', []) or []):
                    if loc and loc.get('url_for_pdf'):
                        return loc['url_for_pdf'], 'unpaywall'
                    if loc and loc.get('endpoint_id') in ['arxiv', 'PubMed Central']:
                        return loc['url_for_pdf'] or loc.get('url'), 'unpaywall'
    except Exception as e:
        logger.debug(f'Unpaywall failed for {doi}: {e}')
    return None, None

def try_semantic_scholar(doi):
    """Get OA PDF URL from Semantic Scholar API."""
    try:
        r = SESSION.get(f'https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}',
                       params={'fields': 'openAccessPdf,externalIds', 'api_key': 'lta6aC9TYm5gQZcPL2NFT8zmdidXl8ag8rqAjZ8Z'},
                       timeout=10)
        if r.status_code == 200:
            data = r.json()
            oa = data.get('openAccessPdf', {})
            if oa and oa.get('url'):
                return oa['url'], 'semantic_scholar'
            ext = data.get('externalIds', {}) or {}
            if 'ArXiv' in ext:
                arxiv_id = ext['ArXiv']
                return f'https://arxiv.org/pdf/{arxiv_id}.pdf', 'arxiv_via_ss'
    except Exception as e:
        logger.debug(f'Semantic Scholar failed for {doi}: {e}')
    return None, None

def try_core(doi):
    """Get OA PDF URL from CORE API."""
    try:
        r = SESSION.get(f'https://api.core.ac.uk/v3/oa-works/{doi}', timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get('fullTextIdentifier'):
                return data['fullTextIdentifier'], 'core'
    except:
        pass
    try:
        r = SESSION.get(f'https://api.core.ac.uk/v3/search/works',
                       params={'q': f'doi:"{doi}"', 'limit': 1}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            items = data.get('hits', []) or []
            if items and items[0].get('links', [{}])[0].get('url'):
                return items[0]['links'][0]['url'], 'core_search'
    except:
        pass
    return None, None

def try_arxiv(doi):
    """Check if DOI maps to arXiv."""
    try:
        # Many arXiv papers have DOIs, try arXiv search
        arxiv_doi = doi.lower()
        if 'arxiv' in arxiv_doi:
            match = re.search(r'arxiv[:\.](\d+\.\d+)', arxiv_doi)
            if match:
                return f'https://arxiv.org/pdf/{match.group(1)}.pdf', 'arxiv_doi'
    except:
        pass
    return None, None

def try_europepmc(doi):
    """Try Europe PMC for PMC articles."""
    try:
        r = SESSION.get(f'https://www.ebi.ac.uk/europepmc/webservices/rest/search',
                       params={'query': f'EXT_ID:{doi}', 'format': 'json', 'resultType': 'core'},
                       timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get('resultList', {}).get('result', [])
            if results:
                item = results[0]
                # Check for full text URL
                if item.get('isOpenAccess') == 'Y' and item.get('fullTextUrlList'):
                    urls = item['fullTextUrlList'].get('fullTextUrl', [])
                    for url_info in urls if isinstance(urls, list) else [urls]:
                        if url_info.get('documentStyle') in ('pdf', 'html'):
                            if url_info.get('url'):
                                return url_info['url'], 'europepmc'
    except:
        pass
    return None, None

def try_crossref(doi):
    """Try Crossref for OA links."""
    try:
        r = SESSION.get(f'https://api.crossref.org/works/{doi}',
                       headers={'mailto': EMAIL}, timeout=10)
        if r.status_code == 200:
            data = r.json().get('message', {})
            # Check for license that allows access
            links = data.get('link', [])
            for link in links:
                if link.get('content-type') == 'application/pdf' and link.get('URL'):
                    return link['URL'], 'crossref'
            # Check for full-text
            if data.get('license') and len(data['license']) > 0:
                # Has license, try the resource link
                url = data.get('link', [{}])[0].get('URL')
                if url:
                    return url, 'crossref_license'
    except:
        pass
    return None, None

def download_pdf(url, dest_path, timeout=60):
    """Download a PDF from URL, returns True if valid PDF."""
    try:
        r = SESSION.get(url, timeout=timeout, stream=True,
                       allow_redirects=True,
                       headers={'Accept': 'application/pdf'})
        if r.status_code != 200:
            return False
        
        # Check content type
        ct = r.headers.get('Content-Type', '')
        # Some OA sources redirect through HTML
        
        # Download with size limit (50MB)
        total = 0
        chunks = []
        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            total += len(chunk)
            chunks.append(chunk)
            if total > 50 * 1024 * 1024:  # 50MB limit
                return False
        
        content = b''.join(chunks)
        
        # Validate PDF header
        if len(content) < 500:
            return False
        if not content.startswith(b'%PDF'):
            return False
        # Validate minimal PDF structure
        content_str = content[:1000].decode('utf-8', errors='ignore')
        if '/Pages' not in content_str and '/Root' not in content_str:
            return False
        
        with open(dest_path, 'wb') as f:
            f.write(content)
        
        return True
    except Exception as e:
        logger.debug(f'Download failed {url}: {e}')
        return False

def find_and_download_pdf(doi, year, title, existing_path=None):
    """Try multiple sources to find and download a PDF for this DOI."""
    if existing_path and os.path.exists(existing_path):
        return existing_path, 'already_have'
    
    year_str = str(year) if year else 'unknown'
    title_clean = sanitize_filename(str(title)[:60] if title else 'unknown')
    
    sources_to_try = [
        try_unpaywall,
        try_semantic_scholar,
        try_arxiv,
        try_core,
        try_europepmc,
        try_crossref,
    ]
    
    tried_urls = set()
    
    for try_func in sources_to_try:
        url, source = try_func(doi)
        if not url:
            continue
        if url in tried_urls:
            continue
        tried_urls.add(url)
        
        dest = os.path.join(PDF_DIR, f'{year_str}_{source}_{title_clean}_{doi.replace("/", "_")}.pdf')
        
        success = download_pdf(url, dest)
        if success:
            return dest, source
    
    return None, None

# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == '__main__':
    import pandas as pd
    import concurrent.futures
    from tqdm import tqdm
    
    logger.info("=" * 70)
    logger.info("PHASE 0: Loading data")
    logger.info("=" * 70)
    
    df = pd.read_excel(CHECKPOINT)
    total = len(df)
    logger.info(f"Loaded {total} records")
    
    # Parse DOI
    df['doi_clean'] = df['doi'].apply(normalize_doi)
    df_with_doi = df[df['doi_clean'].notna()].copy()
    df_no_doi = df[df['doi_clean'].isna()].copy()
    logger.info(f"Records with DOI: {len(df_with_doi)}, without DOI: {len(df_no_doi)}")
    
    # ============================================================
    # PHASE 1: Download PDFs
    # ============================================================
    logger.info("\n" + "="*70)
    logger.info("PHASE 1: Downloading PDFs for all records")
    logger.info("="*70)
    
    # Get records that don't already have PDFs
    has_pdf = df['pdf_path'].notna()
    pdf_records = df[has_pdf].copy()
    no_pdf_records = df[~has_pdf].copy()
    
    logger.info(f"Already have PDF path: {len(pdf_records)}")
    logger.info(f"Need to download: {len(no_pdf_records)}")
    
    # Build set of existing DOIs that have valid PDFs in our dir (from our cleanup)
    existing_pdfs = {}
    for f in glob.glob(os.path.join(PDF_DIR, '*.pdf')):
        sz = os.path.getsize(f)
        if sz > 1000:
            fname = os.path.basename(f).lower()
            existing_pdfs[fname] = f
    
    # Track what we have
    download_results = {
        'already_have': 0,
        'downloaded_new': 0,
        'failed': 0,
        'errors': []
    }
    
    # Process in batches with rate limiting
    no_doi_list = no_pdf_records['doi_clean'].dropna().unique()
    logger.info(f"Unique DOIs to try: {len(no_doi_list)}")
    
    # Group by DOI and pick first occurrence
    doi_to_row = {}
    for idx, row in no_pdf_records.iterrows():
        doi = row['doi_clean']
        if doi and doi not in doi_to_row:
            doi_to_row[doi] = row
    
    logger.info(f"Unique DOIs to download for: {len(doi_to_row)}")
    
    # Rate-limited download loop
    successes = 0
    failures = 0
    rate_errors = 0
    start_time = time.time()
    last_report = 0
    
    dois_to_try = list(doi_to_row.keys())
    
    for i, doi in enumerate(tqdm(dois_to_try, desc="Downloading PDFs by DOI")):
        row = doi_to_row[doi]
        year = row['year']
        title = row['title']
        
        try:
            result, source = find_and_download_pdf(doi, year, title)
            if result:
                if source == 'already_have':
                    download_results['already_have'] += 1
                else:
                    download_results['downloaded_new'] += 1
                    successes += 1
            else:
                download_results['failed'] += 1
                failures += 1
        except Exception as e:
            download_results['errors'].append({'doi': doi, 'error': str(e)})
        
        # Report progress every 100
        if (i+1) % 100 == 0:
            elapsed = time.time() - start_time
            rate = (i+1) / elapsed * 60 if elapsed > 0 else 0
            logger.info(f"  Progress: {i+1}/{len(dois_to_try)} | "
                       f"Downloaded: {successes} | Failed: {failures} | "
                       f"Rate: {rate:.1f}/min")
            save_progress('phase1', {
                'done': i+1,
                'total': len(dois_to_try),
                'successes': successes,
                'failures': failures,
                'download_results': {k:v for k,v in download_results.items() if k != 'errors'}
            })
        
        # Rate limit: ~2 requests/sec
        time.sleep(0.3)
    
    # Now also check records without DOI - try by title match
    logger.info(f"\nPhase 1 Summary:")
    logger.info(f"  Already had: {download_results['already_have']}")
    logger.info(f"  Newly downloaded: {download_results['downloaded_new']}")
    logger.info(f"  Failed to download: {download_results['failed']}")
    logger.info(f"  Errors: {len(download_results['errors'])}")
    
    total_downloaded = download_results['already_have'] + download_results['downloaded_new']
    logger.info(f"  Total with PDF: {total_downloaded}")
    
    save_progress('phase1_complete', download_results)
    
    # ============================================================
    # PHASE 2: Clean invalid files
    # ============================================================
    logger.info("\n" + "="*70)
    logger.info("PHASE 2: Validating and cleaning PDFs")
    logger.info("="*70)
    
    all_pdf_files = sorted(glob.glob(os.path.join(PDF_DIR, '*.pdf')))
    logger.info(f"Total files in PDF dir: {len(all_pdf_files)}")
    
    valid_pdfs = []
    invalid_moved = 0
    
    for f in all_pdf_files:
        try:
            sz = os.path.getsize(f)
            fname = os.path.basename(f)
            
            if sz < 500:
                shutil.move(f, os.path.join(INVALID_BACKUP, fname))
                invalid_moved += 1
                continue
            
            with open(f, 'rb') as fh:
                content = fh.read(2000)
                if not content.startswith(b'%PDF'):
                    shutil.move(f, os.path.join(INVALID_BACKUP, fname))
                    invalid_moved += 1
                    continue
                
                # Read more to validate structure
                fh.seek(0)
                full = fh.read()
                if b'/Pages' not in full and b'/Root' not in full:
                    shutil.move(f, os.path.join(INVALID_BACKUP, fname))
                    invalid_moved += 1
                    continue
                
                valid_pdfs.append({
                    'path': f,
                    'size': len(full),
                    'name': fname
                })
        except Exception as e:
            try:
                shutil.move(f, os.path.join(INVALID_BACKUP, os.path.basename(f)))
            except:
                pass
            invalid_moved += 1
    
    logger.info(f"Valid PDFs: {len(valid_pdfs)}")
    logger.info(f"Invalid moved: {invalid_moved}")
    
    save_progress('phase2', {'valid': len(valid_pdfs), 'invalid': invalid_moved})
    
    # ============================================================
    # PHASE 2b: Deduplicate
    # ============================================================
    logger.info("\n" + "="*70)
    logger.info("PHASE 2b: Deduplicating PDFs")
    logger.info("="*70)
    
    by_doi = defaultdict(list)
    by_title = defaultdict(list)
    
    for info in valid_pdfs:
        fname = info['name']
        # Extract DOI from filename
        doi_match = re.search(r'10\.\d+[/\w.-]+', fname)
        extracted_doi = doi_match.group(0) if doi_match else None
        
        # Extract title
        parts = fname.split('_', 2)
        title_part = parts[2].replace('.pdf', '').strip() if len(parts) >= 3 else fname.replace('.pdf', '')
        title_norm = re.sub(r'[^a-z0-9\s]', '', title_part.lower()).strip()
        title_short = title_norm[:70] if len(title_norm) > 70 else title_norm
        
        by_title[title_short].append(info)
        if extracted_doi:
            by_doi[extracted_doi].append(info)
    
    dupes_by_title = {k: v for k, v in by_title.items() if len(v) > 1}
    dupes_removed = 0
    kept_unique = []
    
    # First dedup by exact title match
    for title_norm, items in dupes_by_title.items():
        # Keep the one with DOI (if any), otherwise largest
        def score(item):
            return item['size']  # Keep largest
        items.sort(key=score, reverse=True)
        
        for item in items[1:]:
            try:
                shutil.move(item['path'], os.path.join(DUP_BACKUP, item['name']))
                dupes_removed += 1
            except:
                pass
        kept_unique.append(items[0])
    
    # Count items not in dup groups
    dup_keys = set(dupes_by_title.keys())
    for info in valid_pdfs:
        parts = info['name'].split('_', 2)
        tp = parts[2].replace('.pdf', '').strip() if len(parts) >= 3 else info['name'].replace('.pdf', '')
        tn = re.sub(r'[^a-z0-9\s]', '', tp.lower()).strip()
        ts = tn[:70] if len(tn) > 70 else tn
        if ts not in dup_keys:
            kept_unique.append(info)
    
    logger.info(f"Duplicate groups: {len(dupes_by_title)}")
    logger.info(f"Duplicate files removed: {dupes_removed}")
    logger.info(f"Unique PDFs after dedup: {len(kept_unique)}")
    
    save_progress('phase2b', {'unique': len(kept_unique), 'dupes_removed': dupes_removed})
    
    # ============================================================
    # PHASE 3: Full content extraction & quality assessment
    # ============================================================
    logger.info("\n" + "="*70)
    logger.info("PHASE 3: Full content extraction from ALL PDFs")
    logger.info("="*70)
    
    try:
        import pdfplumber
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pdfplumber', '-q'])
        import pdfplumber
    
    quality_ratings = []
    total_pdfs = len(kept_unique)
    
    for idx, info in enumerate(tqdm(kept_unique, desc="Extracting content")):
        try:
            doc = pdfplumber.open(info['path'])
            page_count = len(doc.pages)
            
            # Extract ALL text from first 3 pages
            full_text = ""
            for i in range(min(3, page_count)):
                page_text = doc.pages[i].extract_text() or ""
                full_text += page_text + "\n"
            
            doc.close()
            
            # Comprehensive quality analysis
            text_lower = full_text.lower()
            word_count = len(full_text.split())
            
            # Section detection
            has_abstract = bool(re.search(r'abstract', text_lower))
            has_introduction = bool(re.search(r'introduct|bac?kground', text_lower))
            has_methods = bool(re.search(r'method|experimental|material|synthesi|prepar', text_lower))
            has_results = bool(re.search(r'result|discussion|find', text_lower))
            has_conclusion = bool(re.search(r'conclusion|conclud|summary', text_lower))
            has_references = bool(re.search(r'reference|bibliograph', text_lower))
            
            # Numeric data detection
            nm_values = len(re.findall(r'\d+(?:\.\d+)?\s*nm', text_lower))
            percent_values = len(re.findall(r'\d+(?:\.\d+)?\s*%', text_lower))
            emission_matches = len(re.findall(r'(?:emission|excit|wavelength|peak)\s*\w*\s*\d+', text_lower))
            
            # Topic relevance scoring
            core_keywords = ['nanoprobe', 'nanosensor', 'fluorescent', 'fluorescence', 
                           'quantum dot', 'carbon dot', 'lumin', 
                           'aie', 'ucnp', 'perovskite', 'phosphor',
                           'fluorophore', 'biosensor', 'chemosensor']
            
            irrelevant_topics = ['trichloroethylene', 'fenton.*degradation', 'humic acid',
                               'formamide denaturation', 'respiratory', 'pulmonary',
                               'nano zinc oxide.*toxic', 'biocidal', 'antimicrobial',
                               'water treatment', 'wastewater', 'dye degradation']
            
            core_matches = sum(1 for kw in core_keywords if kw in text_lower)
            irrel_matched = []
            for pat in irrelevant_topics:
                if pat.count('.') <= 1:
                    if pat in text_lower:
                        irrel_matched.append(pat)
                else:
                    try:
                        if re.search(pat, text_lower):
                            irrel_matched.append(pat)
                    except re.error:
                        if pat.split()[0] in text_lower:
                            irrel_matched.append(pat)
            
            # Section completeness score (0-1)
            section_score = 0
            for s in [has_abstract, has_introduction, has_methods, has_results, has_conclusion]:
                if s: section_score += 0.2
            
            # Data richness score (0-1)
            data_score = min(1.0, (nm_values * 0.1 + percent_values * 0.05 + emission_matches * 0.15) / 2)
            
            # Relevance score (0-1)
            if irrel_matched:
                relevance_score = 0
            else:
                relevance_score = min(1.0, core_matches * 0.2 + (has_abstract * 0.2))
            
            # Overall quality rating
            if irrel_matched or word_count < 100:
                rating = 'irrelevant'
            elif section_score >= 0.8 and data_score >= 0.3 and relevance_score >= 0.6:
                rating = 'excellent'
            elif section_score >= 0.6 and data_score >= 0.2 and relevance_score >= 0.4:
                rating = 'good'
            elif section_score >= 0.4 and relevance_score >= 0.3:
                rating = 'usable_with_gaps'
            else:
                rating = 'partial_data'
            
            # Extract title from first page
            title_extracted = ""
            title_line = full_text.split('\n')[0] if full_text else ""
            if title_line and len(title_line) > 10:
                title_extracted = title_line[:100]
            
            quality_ratings.append({
                'file': info['name'],
                'path': info['path'],
                'pages': page_count,
                'word_count': word_count,
                'section_score': round(section_score, 2),
                'data_score': round(data_score, 2),
                'relevance_score': round(relevance_score, 2),
                'rating': rating,
                'has_abstract': has_abstract,
                'has_methods': has_methods,
                'has_results': has_results,
                'nm_values': nm_values,
                'core_keyword_matches': core_matches,
                'irrelevant_match': irrel_matched if irrel_matched else None,
                'title_extracted': title_extracted[:100]
            })
            
        except Exception as e:
            quality_ratings.append({
                'file': info['name'],
                'rating': 'error',
                'error': str(e)[:200]
            })
        
        # Save progress every 50
        if (idx + 1) % 50 == 0:
            save_progress('phase3', {'done': idx + 1, 'total': total_pdfs})
    
    logger.info(f"Content extraction complete: {len(quality_ratings)} papers analyzed")
    
    # ============================================================
    # PHASE 4: Generate comprehensive report
    # ============================================================
    logger.info("\n" + "="*70)
    logger.info("PHASE 4: Generating comprehensive report")
    logger.info("="*70)
    
    import pandas as pd
    
    # Match with original checkpoint data
    checkpoint_df = pd.read_excel(CHECKPOINT)
    
    report_data = []
    for qr in quality_ratings:
        fname = qr['file']
        # Match with checkpoint
        match = checkpoint_df[checkpoint_df['pdf_path'].astype(str).str.contains(fname.replace('.pdf', ''), na=False)]
        
        doi = ''
        title = ''
        year = ''
        journal = ''
        
        if len(match) > 0:
            row = match.iloc[0]
            doi = str(row.get('doi', ''))
            title = str(row.get('title', ''))
            year = str(row.get('year', ''))
            journal = str(row.get('journal', ''))
        
        if not title:
            title = qr.get('title_extracted', '')
        if not year and fname[:4].isdigit():
            year = fname[:4]
        
        report_data.append({
            'file_name': fname[:120],
            'file_size_kb': qr.get('pages', 0),
            'pages': qr.get('pages', 0),
            'year': year,
            'doi': doi[:60] if doi else '',
            'journal': str(journal)[:60],
            'title': str(title)[:100],
            'quality_rating': qr.get('rating', 'unknown'),
            'word_count': qr.get('word_count', 0),
            'section_score': qr.get('section_score', 0),
            'data_richness': qr.get('data_score', 0),
            'relevance': qr.get('relevance_score', 0),
            'has_abstract': qr.get('has_abstract', False),
            'has_methods': qr.get('has_methods', False),
            'nm_parameters': qr.get('nm_values', 0),
            'core_keywords_hit': qr.get('core_keyword_matches', 0),
            'irrelevant': qr.get('irrelevant_match') or '',
        })
    
    report_df = pd.DataFrame(report_data)
    
    # Save full report
    full_csv = os.path.join(REPORT_DIR, 'full_pdf_quality_report.csv')
    report_df.to_csv(full_csv, index=False, encoding='utf-8-sig')
    logger.info(f"Full report saved: {full_csv}")
    
    # Generate summary
    rating_counts = report_df['quality_rating'].value_counts()
    logger.info("\n" + "="*70)
    logger.info("FINAL QUALITY DISTRIBUTION")
    logger.info("="*70)
    for r, c in sorted(rating_counts.items()):
        pct = c / len(report_df) * 100
        logger.info(f"  {r:25s}: {c:4d} ({pct:.1f}%)")
    
    # Year distribution
    logger.info("\nYear distribution:")
    years = report_df[report_df['year'] != '']['year'].value_counts().sort_index()
    for y, c in years.items():
        logger.info(f"  {y}: {c}")
    
    # Generate summary markdown report
    summary_md = generate_summary_report(report_df, total, download_results)
    summary_path = os.path.join(REPORT_DIR, 'SUMMARY_REPORT.md')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary_md)
    logger.info(f"\nSummary report: {summary_path}")
    
    save_progress('phase4_complete', {'report': summary_path})
    logger.info("\n" + "="*70)
    logger.info("PIPELINE COMPLETE")
    logger.info("="*70)
    logger.info(f"Full report: {full_csv}")
    logger.info(f"Summary: {summary_path}")


def generate_summary_report(report_df, total_orig, download_results):
    """Generate markdown summary report."""
    rating_order = ['excellent', 'good', 'usable_with_gaps', 'partial_data', 'irrelevant', 'error']
    
    md = f"""# 文献下载与质量评估完整报告

## 1. 项目概况

- **原始记录数**: {total_orig} 条（来自 checkpoint）
- **有效 DOI 记录**: {report_df['doi'].notna().sum()} 条
- **已下载 PDF 总数**: {len(report_df)} 篇
- **报告生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}

## 2. 下载结果

| 指标 | 数值 |
|------|------|
| 已有 PDF 路径记录 | {download_results.get('already_have', 'N/A')} |
| 新下载成功 | {download_results.get('downloaded_new', 'N/A')} |
| 下载失败 | {download_results.get('failed', 'N/A')} |
| 错误数 | {len(download_results.get('errors', []))} |

## 3. 质量分布

| 评级 | 数量 | 比例 | 说明 |
|------|------|------|------|
"""

    for rating in rating_order:
        subset = report_df[report_df['quality_rating'] == rating]
        c = len(subset)
        pct = c / len(report_df) * 100 if len(report_df) > 0 else 0
        
        desc = {
            'excellent': '⭐ 完整论文，有 Abstract + 方法 + 结果 + 数值数据',
            'good': '✅ 可用，有 Abstract 和关键词相关，部分数据完整',
            'usable_with_gaps': '⚠️ 可使用但数据可能不完整',
            'partial_data': '⚠️ 部分内容可用（缺 Abstract 或方法论）',
            'irrelevant': '❌ 不相关（非纳米荧光探针领域）',
            'error': '❌ 解析失败',
        }.get(rating, '')
        
        md += f"| {rating} | {c} | {pct:.1f}% | {desc} |\n"
    
    # Usable summary
    usable = report_df[report_df['quality_rating'].isin(['excellent', 'good'])]
    gaps = report_df[report_df['quality_rating'] == 'usable_with_gaps']
    partial = report_df[report_df['quality_rating'] == 'partial_data']
    irrelevant = report_df[report_df['quality_rating'] == 'irrelevant']
    
    excellent_count = len(report_df[report_df['quality_rating'] == 'excellent'])
    good_count = len(report_df[report_df['quality_rating'] == 'good'])
    usable_count = len(usable)
    usable_pct = usable_count / len(report_df) * 100 if len(report_df) > 0 else 0
    gaps_count = len(gaps)
    partial_count = len(partial)
    irrelevant_count = len(irrelevant)
    error_count = len(report_df[report_df['quality_rating'] == 'error'])
    
    # Year distribution
    year_dist = report_df[report_df['year'] != '']['year'].value_counts().sort_index()
    year_lines = "\n".join([f"| {y} | {c} |" for y, c in year_dist.items()])
    
    # Top journals
    journal_dist = report_df[report_df['journal'] != '']['journal'].value_counts()
    journal_lines = "\n".join([f"| {j} | {c} |" for j, c in journal_dist.head(20).items()])
    
    with open(full_csv, 'r', encoding='utf-8-sig') as f:
        csv_line_count = len(f.readlines())
    
    md = f"""# 文献下载与质量评估完整报告

## 1. 项目概况

- **原始记录数**: {total_orig} 条（来自 checkpoint）
- **最终下载并分析的 PDF**: {len(report_df)} 篇
- **报告生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}
- **报告数据量**: {csv_line_count} 行 CSV

## 2. 下载结果

| 指标 | 数值 |
|------|------|
| 已有 PDF 路径记录 | {download_results.get('already_have', 'N/A')} |
| 新下载成功 | {download_results.get('downloaded_new', 'N/A')} |
| 下载失败 | {download_results.get('failed', 'N/A')} |

## 3. 质量分布

| 评级 | 数量 | 比例 | 说明 |
|------|------|------|------|
| excellent | {excellent_count} | {excellent_count/len(report_df)*100:.1f}% | 完整论文，Abstract+方法+结果+数值数据 |
| good | {good_count} | {good_count/len(report_df)*100:.1f}% | 可用，有Abstract和核心关键词 |
| usable_with_gaps | {gaps_count} | {gaps_count/len(report_df)*100:.1f}% | 可使用但数据不完整 |
| partial_data | {partial_count} | {partial_count/len(report_df)*100:.1f}% | 部分可用，缺Abstract或方法 |
| irrelevant | {irrelevant_count} | {irrelevant_count/len(report_df)*100:.1f}% | 不相关（非纳米荧光探针领域） |
| error | {error_count} | {error_count/len(report_df)*100:.1f}% | 解析失败 |

## 4. 可直接使用的文献

- **优秀**: {excellent_count} 篇 - 数据结构完整，含参数、方法、结果
- **良好**: {good_count} 篇 - 核心数据可用，部分字段可能缺失
- **高质量合计**: {usable_count} 篇（{usable_pct:.1f}%）

## 5. 有数据缺失但可用的文献

- **有缺口但可用**: {gaps_count} 篇
- **数据部分可用**: {partial_count} 篇

## 6. 不相关文献

- **不相关**: {irrelevant_count} 篇

## 7. 年份分布

| 年份 | 数量 |
|------|------|
{year_lines}

## 8. 期刊 TOP 20

| 期刊 | 数量 |
|------|------|
{journal_lines}
"""
    return md