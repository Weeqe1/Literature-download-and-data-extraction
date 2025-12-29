# harvest_literature.py
# Harvester for literature across OpenAlex, WoS, Semantic Scholar, PubMed, arXiv, Crossref.
# Features:
#  - Split long keywords into clauses by top-level OR (preserve internal AND)
#  - Two-phase search per clause: title-only then title+abstract
#  - Search order configurable (via configs/harvest_config.yml)
#  - Merge + deduplicate works, use Crossref to fill missing DOIs
#  - Incremental mode: read existing Excel, skip already-recorded DOIs
#  - Download OA PDFs (Unpaywall / best_oa_location / pdf_url fields), save PDFs
#  - PDF integrity check and removal of broken PDFs + update Excel
#  - Output Excel with extended columns
#
# Configuration: Edit configs/harvest_config.yml to customize search parameters
#
# Dependencies:
# pip install requests tqdm pandas PyPDF2 python-dateutil rapidfuzz tenacity lxml pyyaml

import os
import re
import time
import shutil
import requests
import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus
import pandas as pd
from tqdm import tqdm
from dateutil import parser as dtparser
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# optional: PyPDF2 for PDF validation
try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None

# Optional fuzzy title matching (used for Crossref DOI fill)
try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

# Optional YAML for config loading
try:
    import yaml
except Exception:
    yaml = None

# -------------
# Config Loading
# -------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "configs", "harvest", "harvest_config.yml")
_config = {}

def load_config():
    """Load configuration from configs/harvest_config.yml"""
    global _config
    if yaml is None:
        print("[Warning] PyYAML not installed. Using default config values.")
        return {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                _config = yaml.safe_load(f) or {}
            print(f"[Config] Loaded configuration from {CONFIG_PATH}")
        except Exception as e:
            print(f"[Warning] Failed to load config: {e}. Using defaults.")
            _config = {}
    else:
        print(f"[Warning] Config file not found: {CONFIG_PATH}. Using defaults.")
        _config = {}
    return _config

def get_config(key_path: str, default=None):
    """Get a config value by dot-separated path, e.g. 'search.year_from'"""
    keys = key_path.split(".")
    val = _config
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            return default
    return val if val is not None else default

# Load config on module import
load_config()

# -------------
# Config Values (from file or defaults)
# -------------
WOS_API_KEY = os.environ.get("WOS_API_KEY", get_config("api_keys.wos", ""))
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", get_config("api_keys.semantic_scholar", ""))
DEFAULT_EMAIL = get_config("api_keys.contact_email", "wangqi@ahut.edu.cn")

# HTTP session
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "harvest_literature/1.0 (mailto:%s)" % DEFAULT_EMAIL})
REQS_PER_SECOND = get_config("runtime.requests_per_second", 4)
MIN_SLEEP = 1.0 / max(1, REQS_PER_SECOND)

def rate_limit():
    time.sleep(MIN_SLEEP)

# -----------------------
# Utilities
# -----------------------
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:200]

def doi_normalize(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip()
    if doi.startswith("http"):
        m = re.search(r"10\.\d{4,9}/\S+", doi)
        if m:
            return m.group(0)
    return doi

def safe_get(d: dict, *keys, default=None):
    x = d
    for k in keys:
        if not x:
            return default
        x = x.get(k, None) if isinstance(x, dict) else default
    return x if x is not None else default

# -----------------------
# Clause splitting (the rule you requested)
# Top-level OR split: when keywords = '("A") OR ("B") OR ("C" AND "D")'
# result -> ["\"A\"", "\"B\"", "\"C\" AND \"D\""]
# Implementation: scan string, track parentheses depth and quoted strings, split on OR at depth==0
# -----------------------
def split_keywords_into_clauses(keywords: str, max_clauses: int = 200) -> List[str]:
    """
    Split a boolean keyword string by top-level OR separators while preserving internal AND groups.
    Top-level separators: OR (case-insensitive) and commas at top parentheses depth.
    Returns a list of clause strings (trimmed), each clause may contain AND/NOT internally.
    """
    if not keywords or not keywords.strip():
        return []

    s = keywords.replace("“", '"').replace("”", '"').strip()

    parts = []
    cur = []
    depth = 0
    i = 0
    L = len(s)
    while i < L:
        ch = s[i]
        # quoted string handling
        if ch == '"':
            cur.append(ch)
            i += 1
            while i < L:
                cur.append(s[i])
                if s[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        # parentheses depth
        if ch == '(':
            depth += 1
            cur.append(ch)
            i += 1
            continue
        if ch == ')':
            depth = max(0, depth - 1)
            cur.append(ch)
            i += 1
            continue
        # top-level OR detection
        if depth == 0:
            m = re.match(r'\s+OR\s+', s[i:], flags=re.I)
            if m:
                fragment = ''.join(cur).strip()
                if fragment:
                    parts.append(fragment)
                cur = []
                i += m.end()
                continue
            # accept commas as top-level separators
            if ch == ',':
                fragment = ''.join(cur).strip()
                if fragment:
                    parts.append(fragment)
                cur = []
                i += 1
                continue
        cur.append(ch)
        i += 1
    if cur:
        fragment = ''.join(cur).strip()
        if fragment:
            parts.append(fragment)

    # strip outer parentheses that enclose whole fragment
    def strip_outer_parens(p: str) -> str:
        p = p.strip()
        while p.startswith('(') and p.endswith(')'):
            inner = p[1:-1].strip()
            # check balance inside
            bal = 0
            ok = True
            for c in inner:
                if c == '(':
                    bal += 1
                elif c == ')':
                    bal -= 1
                    if bal < 0:
                        ok = False
                        break
            if not ok or bal != 0:
                break
            p = inner
        return p

    cleaned = []
    seen = set()
    for p in parts:
        p2 = strip_outer_parens(p).strip()
        if not p2:
            continue
        # drop pure logical tokens
        if re.fullmatch(r'^(AND|OR|NOT|\s)+$', p2, flags=re.I):
            continue
        # require some content
        if len(re.sub(r'[^A-Za-z0-9]', '', p2)) < 3:
            continue
        key = p2.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(p2)
    return cleaned[:max_clauses]

# -----------------------
# OpenAlex search
# -----------------------
OPENALEX_BASE = "https://api.openalex.org/works"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), retry=retry_if_exception_type((requests.RequestException,)))
def openalex_get(params: dict):
    rate_limit()
    r = SESSION.get(OPENALEX_BASE, params=params, timeout=30)
    if r.status_code != 200:
        raise requests.RequestException(f"OpenAlex HTTP {r.status_code}: {r.text[:300]}")
    return r.json()

def search_openalex_clause(clause: str, max_results: int = 200, title_only: bool = False, year_from: Optional[int] = None, year_to: Optional[int] = None, mailto: Optional[str] = None) -> List[dict]:
    """
    Search OpenAlex for a clause. If title_only True, use title.search; otherwise search abstract as well.
    Returns list of works (raw dicts).
    """
    results = []
    per_page = 50
    page = 1
    field_names = []
    if title_only:
        field_names.append("title.search")
    else:
        # will try title.search and abstract.search separately in caller
        field_names = [None]  # fallback to broad search
    # But we implement two runs in caller; here do a broad call
    params = {"per-page": per_page, "page": page, "select": ",".join([
        "id","doi","display_name","title","abstract_inverted_index","publication_year","publication_date",
        "best_oa_location","open_access","authorships","type","language","is_paratext","cited_by_count"
    ])}
    if mailto:
        params["mailto"] = mailto
    # Use search param (OpenAlex supports 'search' and 'filter')
    params["search"] = clause
    if year_from and year_to:
        params["filter"] = f"publication_year:{year_from}-{year_to}"
    elif year_from:
        params["filter"] = f"publication_year:>={year_from}"
    elif year_to:
        params["filter"] = f"publication_year:<={year_to}"
    # iterate pages
    while len(results) < max_results:
        params["page"] = page
        try:
            js = openalex_get(params)
        except Exception as e:
            # give up gracefully
            break
        works = js.get("results", [])
        if not works:
            break
        for w in works:
            # minimal filtering: if title_only is requested by caller, enforce local check
            results.append(w)
            if len(results) >= max_results:
                break
        page += 1
        if page > 200:
            break
    return results[:max_results]

# -----------------------
# WoS search (Clarivate APIs)
# -----------------------
WOS_BASE = "https://api.clarivate.com/apis/wos-starter/v1/documents"

def choose_best_wos_db(verbose: bool = True) -> Optional[str]:
    """
    Try some db values to determine a db that returns search results (heuristic).
    """
    api_key = WOS_API_KEY
    if not api_key:
        if verbose:
            print("[WoS] WOS_API_KEY not set; skipping WoS.")
        return None
    headers = {"X-ApiKey": api_key, "Accept": "application/json"}
    candidates = ["WOS", "MEDLINE", "BIOSIS", "WOK", "WOSCC"]
    test_q = 'TS=("nano fluorescent probe")'
    for db in candidates:
        params = {"q": test_q, "db": db, "limit": 1, "page": 1}
        try:
            rate_limit()
            r = requests.get(WOS_BASE, headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                try:
                    js = r.json()
                    total = (js.get("metadata") or {}).get("total")
                    if total and int(total) > 0:
                        if verbose:
                            print(f"[WoS-Test][{db}] HTTP 200 total={total}")
                        return db
                except Exception:
                    pass
            else:
                # continue trying other dbs
                pass
        except Exception:
            pass
    return "WOS"  # fallback

def search_wos_clause(clause: str, max_results: int = 200, year_from: Optional[int] = None, year_to: Optional[int] = None, verbose: bool = True) -> List[dict]:
    """
    Search WoS with a single clause. We'll wrap clause into TS=(clause) and do paging.
    Uses choose_best_wos_db to pick a db.
    Returns list of simple dicts with fields: title, doi, journal, publication_year, authors, cited_by_count
    """
    api_key = WOS_API_KEY
    if not api_key:
        if verbose:
            print("[WoS] skip: no API key")
        return []
    db = choose_best_wos_db(verbose=verbose)
    if not db:
        if verbose:
            print("[WoS] choose_best_wos_db returned None; skipping WoS")
        return []
    headers = {"X-ApiKey": api_key, "Accept": "application/json"}
    q_body = clause
    # ensure TS= prefix if not present
    if not re.search(r'\bTS=', q_body):
        q_body = f"TS=({q_body})"
    if year_from and year_to:
        q_body = f"({q_body}) AND PY={year_from}-{year_to}"
    elif year_from:
        q_body = f"({q_body}) AND PY>={year_from}"
    elif year_to:
        q_body = f"({q_body}) AND PY<={year_to}"

    results = []
    page = 1
    page_size = 50
    while len(results) < max_results:
        params = {"q": q_body, "db": db, "limit": page_size, "page": page}
        try:
            rate_limit()
            r = requests.get(WOS_BASE, headers=headers, params=params, timeout=30)
            if r.status_code != 200:
                if verbose:
                    print(f"[WoS] HTTP {r.status_code}: {r.text[:300]}")
                break
            js = r.json()
        except Exception as e:
            if verbose:
                print(f"[WoS] request exception: {e}")
            break
        hits = js.get("hits") or []
        if not hits:
            break
        for item in hits:
            source = item.get("source") or {}
            title = item.get("title") or item.get("titleRaw") or None
            doi = item.get("doi")
            # sometimes identifiers nested
            if not doi:
                for ident in item.get("identifiers") or []:
                    if isinstance(ident, dict) and ident.get("type","").lower() == "doi":
                        doi = ident.get("value") or ident.get("id")
            journal = source.get("sourceTitle") or source.get("title")
            year = source.get("publishYear")
            authors = None
            try:
                if item.get("authors"):
                    authors = ", ".join([a.get("name") for a in item.get("authors") if a.get("name")])
            except Exception:
                authors = None
            cited = item.get("citationCount") or item.get("timesCited")
            results.append({
                "source": "wos",
                "doi": doi,
                "display_name": title,
                "journal": journal,
                "publication_year": int(year) if year and str(year).isdigit() else None,
                "authors": authors,
                "cited_by_count": cited
            })
            if len(results) >= max_results:
                break
        page += 1
        if page > 20:
            break
    return results[:max_results]

# -----------------------
# Semantic Scholar
# -----------------------
def search_semantic_scholar_clause(clause: str, max_results: int = 100, title_only: bool = False, api_key: Optional[str] = None, verbose: bool = True) -> List[dict]:
    """
    Query Semantic Scholar Graph API. Use conservative fields to avoid HTTP 400.
    """
    if api_key is None:
        api_key = SEMANTIC_SCHOLAR_API_KEY
    if not api_key:
        if verbose:
            print("[Semantic Scholar] API key not set; skipping Semantic Scholar")
        return []
    base = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,abstract,year,venue,authors,externalIds,isOpenAccess,openAccessPdf"
    params = {"query": clause, "limit": min(max_results, 100), "fields": fields}
    headers = {"x-api-key": api_key, "User-Agent": "pdf_download_harvester/1.0"}
    attempts = 0
    backoff = 1.0
    while attempts < 5:
        try:
            rate_limit()
            r = requests.get(base, params=params, headers=headers, timeout=25)
        except Exception as e:
            attempts += 1
            time.sleep(backoff)
            backoff *= 2
            continue
        if r.status_code == 200:
            js = r.json()
            items = js.get("data") or js.get("results") or []
            out = []
            for it in items:
                doi = None
                ext = it.get("externalIds") or {}
                if isinstance(ext, dict):
                    doi = ext.get("DOI") or ext.get("doi")
                out.append({
                    "source": "semantic_scholar",
                    "doi": doi,
                    "display_name": it.get("title"),
                    "abstract_text": it.get("abstract"),
                    "publication_year": it.get("year"),
                    "journal": it.get("venue"),
                    "authors_list": [a.get("name") for a in it.get("authors") or []],
                    "open_access_status": it.get("isOpenAccess"),
                    "oa_url": safe_get(it, "openAccessPdf", "url")
                })
            return out
        elif r.status_code == 429:
            attempts += 1
            time.sleep(backoff)
            backoff *= 2
            continue
        else:
            # some 400 may indicate unsupported fields; try minimal fields once
            if r.status_code == 400 and attempts == 0:
                params["fields"] = "title,abstract,year,authors"
                attempts += 1
                continue
            if verbose:
                print(f"[Semantic Scholar] HTTP {r.status_code}: {r.text[:300]}")
            return []
    if verbose:
        print("[Semantic Scholar] persistent failures; skipping")
    return []

# -----------------------
# PubMed (Entrez eutils)
# -----------------------
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
def search_pubmed_clause(clause: str, max_results: int = 200, title_only: bool = False, email: Optional[str] = None) -> List[dict]:
    """
    Use esearch to get ids, then efetch to get summary fields via retmode=xml.
    Clause should be adapted to PubMed syntax; if clause contains quotes treat them as phrase.
    """
    if email is None:
        email = DEFAULT_EMAIL
    term = clause
    params = {"db":"pubmed","term":term,"retmax":min(max_results,200),"retmode":"xml","email":email}
    try:
        rate_limit()
        r = requests.get(PUBMED_ESEARCH, params=params, timeout=25)
        if r.status_code != 200:
            return []
        # parse XML to get IDs
        import xml.etree.ElementTree as ET
        es = ET.fromstring(r.text)
        ids = [idn.text for idn in es.findall(".//IdList/Id")]
        if not ids:
            return []
        # efetch for summaries
        ids_str = ",".join(ids)
        params2 = {"db":"pubmed","id":ids_str,"retmode":"xml"}
        rate_limit()
        r2 = requests.get(PUBMED_EFETCH, params=params2, timeout=30)
        if r2.status_code != 200:
            return []
        root = ET.fromstring(r2.text)
        out = []
        for article in root.findall(".//PubmedArticle"):
            try:
                title = article.findtext(".//ArticleTitle")
                abstract = " ".join([t.text.strip() for t in article.findall(".//AbstractText") if t is not None and t.text])
                journal = article.findtext(".//Journal/Title")
                year = article.findtext(".//Journal/JournalIssue/PubDate/Year")
                doi = None
                for el in article.findall(".//ArticleId"):
                    if el.get("IdType") and el.get("IdType").lower() == "doi":
                        doi = el.text
                authors = []
                for a in article.findall(".//Author"):
                    fn = a.findtext("ForeName") or ""
                    ln = a.findtext("LastName") or ""
                    name = (fn + " " + ln).strip()
                    if name:
                        authors.append(name)
                out.append({
                    "source":"pubmed",
                    "doi":doi,
                    "display_name":title,
                    "abstract_text":abstract,
                    "publication_year": int(year) if year and year.isdigit() else None,
                    "journal":journal,
                    "authors_list": authors
                })
            except Exception:
                continue
        return out
    except Exception:
        return []

# -----------------------
# arXiv
# -----------------------
ARXIV_API = "http://export.arxiv.org/api/query"
def search_arxiv_clause(clause: str, max_results: int = 100, title_only: bool = False) -> List[dict]:
    # Build a simple search: all fields for simplicity
    q = clause
    params = {"search_query": f"all:{q}", "start":0, "max_results": min(max_results,200)}
    try:
        rate_limit()
        r = requests.get(ARXIV_API, params=params, timeout=30)
        if r.status_code != 200:
            return []
        # parse feed (lightweight)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        ns = {"atom":"http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        out = []
        for e in entries:
            title = e.findtext("atom:title", default="", namespaces=ns)
            summary = e.findtext("atom:summary", default="", namespaces=ns)
            doi = None
            for idn in e.findall("atom:link", ns):
                pass
            # year from published
            pub = e.findtext("atom:published", default="", namespaces=ns)
            year = None
            try:
                if pub:
                    year = dtparser.parse(pub).year
            except Exception:
                year = None
            out.append({
                "source":"arxiv",
                "doi": None,
                "display_name": title.strip(),
                "abstract_text": summary.strip(),
                "publication_year": year,
                "journal": "arXiv",
                "authors_list": [a.findtext("atom:name", default="", namespaces=ns) for a in e.findall("atom:author", ns)]
            })
        return out
    except Exception:
        return []

# -----------------------
# Crossref
# -----------------------
CROSSREF_API = "https://api.crossref.org/works"
def search_crossref_clause(clause: str, max_results: int = 200, mailto: Optional[str] = None) -> List[dict]:
    params = {"query": clause, "rows": min(max_results, 1000)}
    if mailto:
        params["mailto"] = mailto
    try:
        rate_limit()
        r = requests.get(CROSSREF_API, params=params, timeout=30)
        if r.status_code != 200:
            return []
        js = r.json()
        items = js.get("message", {}).get("items", [])[:max_results]
        out = []
        for it in items:
            doi = it.get("DOI")
            title = (it.get("title") or [None])[0]
            abstract = it.get("abstract")
            issued = it.get("issued", {}).get("date-parts", [])
            year = issued[0][0] if issued and issued[0] else None
            journal = (it.get("container-title") or [None])[0]
            authors = []
            for a in it.get("author", []) or []:
                authors.append(" ".join([a.get("given",""), a.get("family","")]).strip())
            out.append({
                "source":"crossref",
                "doi":doi,
                "display_name": title,
                "abstract_text": re.sub(r'<[^>]+>', '', abstract) if abstract else None,
                "publication_year": year,
                "journal": journal,
                "authors_list": authors
            })
        return out
    except Exception:
        return []

def crossref_find_doi_by_title(title: str, mailto: Optional[str] = None) -> Optional[str]:
    if not title:
        return None
    params = {"query.title": title, "rows": 5}
    if mailto:
        params["mailto"] = mailto
    try:
        rate_limit()
        r = requests.get(CROSSREF_API, params=params, timeout=25)
        if r.status_code != 200:
            return None
        items = r.json().get("message", {}).get("items", [])[:5]
        best = None
        best_score = 0
        for it in items:
            t = (it.get("title") or [""])[0] or ""
            score = 0
            if fuzz:
                score = fuzz.partial_ratio(t.lower(), title.lower())
            else:
                score = 100 if t.strip().lower() == title.strip().lower() else 0
            if score > best_score:
                best_score = score
                best = it.get("DOI")
        if best and best_score >= 90:
            return best
    except Exception:
        return None
    return None

# -----------------------
# Unpaywall PDF lookup
# -----------------------
UNPAYWALL_API = "https://api.unpaywall.org/v2/"

def get_unpaywall_pdf_by_doi(doi: str, email: str):
    if not doi:
        return None, False
    url = f"{UNPAYWALL_API}{quote_plus(doi)}"
    params = {"email": email}
    try:
        rate_limit()
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None, False
        js = r.json()
        best = js.get("best_oa_location") or {}
        pdf = best.get("url_for_pdf") or best.get("url")
        is_oa = js.get("is_oa")
        return pdf, is_oa
    except Exception:
        return None, False

# -----------------------
# Helper: download file
# -----------------------
def download_file(url: str, out_path: str, timeout: int = 60) -> bool:
    try:
        rate_limit()
        with requests.get(url, stream=True, timeout=timeout) as r:
            if r.status_code != 200:
                return False
            ensure_dir(os.path.dirname(out_path))
            with open(out_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
        return True
    except Exception:
        return False

def ensure_dir(path: str):
    if path:
        os.makedirs(path, exist_ok=True)

# -----------------------
# Merge, dedupe, rows assembly
# -----------------------
def work_to_row(work: dict) -> Dict[str, Any]:
    """
    Turn a raw work dict (from any source) into a normalized row dict for DataFrame.
    """
    row = {}
    row["title"] = work.get("display_name") or work.get("title") or ""
    row["abstract"] = work.get("abstract_text") or work.get("abstract") or ""
    row["journal"] = work.get("journal") or extract_journal_from_work(work) or ""
    row["year"] = work.get("publication_year") or work.get("year") or ""
    row["doi"] = doi_normalize(work.get("doi") or "")
    # authors
    alist = work.get("authors_list") or []
    if not alist and work.get("authorships"):
        alist = [a.get("author",{}).get("display_name") for a in work.get("authorships") or [] if a.get("author")]
    row["authors"] = "; ".join([a for a in alist if a])
    row["affiliations"] = work.get("affiliations") or ""
    row["cited_by_count"] = work.get("cited_by_count") or work.get("timesCited") or None
    row["open_access_status"] = work.get("open_access") or work.get("open_access_status") or work.get("is_oa") or None
    row["pdf_url"] = work.get("oa_url") or safe_get(work, "openAccessPdf", "url") or safe_get(work, "best_oa_location", "url_for_pdf") or safe_get(work, "best_oa_location", "url")
    row["source"] = work.get("source") or ""
    return row

def extract_journal_from_work(work: dict) -> Optional[str]:
    if not work:
        return None
    if work.get("journal"):
        return work.get("journal")
    if work.get("primary_location"):
        return safe_get(work, "primary_location", "source", "display_name")
    if work.get("locations"):
        for loc in work.get("locations") or []:
            s = loc.get("source") or {}
            if s.get("display_name"):
                return s.get("display_name")
    return None

# -----------------------
# PDF Check
# -----------------------
def check_pdf_valid(path: str) -> bool:
    """
    Check if PDF can be opened and has at least 1 page.
    """
    if not os.path.exists(path):
        return False
    if PdfReader is None:
        # best-effort: check file size > 1KB and starts with %PDF
        try:
            with open(path, "rb") as fh:
                head = fh.read(6)
                if not head.startswith(b"%PDF"):
                    return False
                fh.seek(0,2)
                size = fh.tell()
                return size > 1024
        except Exception:
            return False
    try:
        with open(path, "rb") as fh:
            pdf = PdfReader(fh)
            if getattr(pdf, "pages", None) is None:
                return False
            if len(pdf.pages) < 1:
                return False
        return True
    except Exception:
        return False

# -----------------------
# High-level flow: for each clause, run searches (order configurable)
# two rounds: title-only then title+abstract; accumulate results
# -----------------------
def run_clause_search(clause: str, sources_order: List[str], max_per_clause: int = 200, mailto: Optional[str] = None, verbose: bool = True, year_from: Optional[int] = None, year_to: Optional[int] = None, semantic_api_key: Optional[str] = None) -> List[dict]:
    """
    Run the configured sources for a single clause, in two rounds (title-only then title+abstract).
    Each source function is called with a clause string adapted for that source as needed.
    Returns raw works list.
    """
    collected = []

    # clause validity check
    def is_valid_clause(c: str) -> bool:
        if not c or not c.strip():
            return False
        s = c.strip()
        if len(re.sub(r'[^A-Za-z0-9]', '', s)) < 3:
            return False
        if re.fullmatch(r'^(AND|OR|NOT|\s)+$', s, flags=re.I):
            return False
        return True

    if not is_valid_clause(clause):
        if verbose:
            print(f"[RunClause] skipping invalid clause: {clause}")
        return []

    # helper to adapt query for source
    def adapt_for(source: str, c: str, title_only_flag: bool) -> str:
        """
        Normalize clause for specific sources:
          - For semantic_scholar: remove boolean operators, preserve phrase word order
          - For pubmed: leave raw here; search_pubmed_clause will adjust when title_only_flag True
          - For arxiv/crossref: prefer removing explicit boolean operators (use space) for more robust matching
        """
        if source == "semantic_scholar":
            # remove TS= and parentheses, replace boolean operators with spaces,
            # remove surrounding quotes but keep the phrase words together
            s = re.sub(r'\bTS=|\(|\)', ' ', c)
            # replace AND/OR/NOT by single space
            s = re.sub(r'\b(AND|OR|NOT)\b', ' ', s, flags=re.I)
            # remove double quotes but keep words
            s = s.replace('"', ' ')
            s = re.sub(r'\s+', ' ', s).strip()
            return s
        if source == "pubmed":
            # leave raw; search_pubmed_clause will add [Title/Abstract] if needed
            return c
        if source in ("arxiv", "crossref"):
            # prefer space-separated terms for these free-text endpoints
            s = re.sub(r'\b(AND|OR|NOT)\b', ' ', c, flags=re.I).replace('"', ' ')
            s = re.sub(r'\s+', ' ', s).strip()
            return s
        # default: openalex, wos accept clause as-is
        return c

    # wrappers map
    def call_source(src: str, q: str, title_only_flag: bool):
        try:
            if src == "openalex":
                return search_openalex_clause(q, max_results=max_per_clause, title_only=title_only_flag, year_from=year_from, year_to=year_to, mailto=mailto)
            if src == "wos":
                return search_wos_clause(q, max_results=max_per_clause, year_from=year_from, year_to=year_to)
            if src == "semantic_scholar":
                return search_semantic_scholar_clause(q, max_results=max_per_clause, title_only=title_only_flag, api_key=semantic_api_key)
            if src == "pubmed":
                return search_pubmed_clause(q, max_results=max_per_clause, title_only=title_only_flag, email=mailto)
            if src == "arxiv":
                return search_arxiv_clause(q, max_results=max_per_clause, title_only=title_only_flag)
            if src == "crossref":
                return search_crossref_clause(q, max_results=max_per_clause, mailto=mailto)
        except Exception as e:
            if verbose:
                print(f"[{src}] exception: {e}")
        return []

    # Round 1: title-only (many APIs don't have title.search; some use same clause)
    for title_only in (True, False):
        which = "title-only" if title_only else "title+abstract"
        for src in sources_order:
            q = adapt_for(src, clause, title_only)

            if verbose:
                print(f"[{src}] querying ({which}): {q if len(q) < 200 else q[:200] + '...'}")
            items = call_source(src, q, title_only)
            if items:
                if verbose:
                    print(f"[{src}] returned {len(items)} items for clause")
                collected.extend(items)
            else:
                if verbose:
                    print(f"[{src}] returned 0 items for clause")
    return collected

# -----------------------
# Merge & deduplicate works across clauses & sources (score by DOI/title)
# -----------------------
def merge_and_dedupe(works_all: List[dict], max_total: int = 10000) -> List[dict]:
    seen = {}
    merged = []
    for w in works_all:
        doi = doi_normalize(w.get("doi") or "")
        title = (w.get("display_name") or w.get("title") or "").strip().lower()
        key = doi if doi else ("title:" + title)
        if not key:
            continue
        if key in seen:
            # merge metadata: prefer fields present
            old = seen[key]
            for fld in ("abstract_text","journal","publication_year","authors_list","open_access_status","pdf_url","cited_by_count"):
                if not old.get(fld) and w.get(fld):
                    old[fld] = w.get(fld)
            # prefer original source list accumulation
            continue
        seen[key] = w
        merged.append(w)
        if len(merged) >= max_total:
            break
    return merged

# -----------------------
# Fill missing DOIs via Crossref title lookup
# -----------------------
def fill_missing_dois(rows: List[Dict[str, Any]], mailto: Optional[str] = None, verbose: bool = True):
    missing = [r for r in rows if not r.get("doi")]
    if not missing:
        if verbose:
            print("[Fill] no missing DOIs")
        return rows
    if verbose:
        print(f"[Fill] trying to find missing DOIs for {len(missing)} items via Crossref")
    for r in tqdm(missing, desc="Finding DOIs"):
        title = r.get("display_name") or r.get("title") or ""
        if not title:
            continue
        found = crossref_find_doi_by_title(title, mailto=mailto)
        if found:
            r["doi"] = found
    return rows

# -----------------------
# Download OA PDFs and assemble final DataFrame
# -----------------------
def download_pdfs_and_assemble(works: List[dict], out_dir: str, mailto: Optional[str] = None, email: Optional[str] = None) -> pd.DataFrame:
    """
    For each work, attempt to find OA PDF (via oa fields, openAccessPdf, or Unpaywall) and download.
    Build rows and write PDF files into out_dir/PDFs/.
    """
    ensure_dir(out_dir)
    pdf_dir = os.path.join(out_dir, "PDF")
    ensure_dir(pdf_dir)
    rows = []
    for w in tqdm(works, desc="[Download] Processing & Downloading"):
        row = work_to_row(w)
        doi = doi_normalize(row.get("doi") or "")
        pdf_url = row.get("pdf_url")
        # If not pdf_url, try Unpaywall by DOI
        is_oa = False
        if not pdf_url and doi:
            pdf_url, is_oa = get_unpaywall_pdf_by_doi(doi, email or mailto or DEFAULT_EMAIL)
        elif pdf_url:
            is_oa = True
        row["is_oa"] = bool(is_oa)
        # attempt download
        out_file = None
        if pdf_url:
            fn_title = sanitize_filename(f"{row.get('year')}_{row.get('journal')}_{row.get('title') or row.get('display_name') or 'paper'}.pdf")
            out_file = os.path.join(pdf_dir, fn_title)
            ok = download_file(pdf_url, out_file)
            if not ok:
                # try heuristics: some OA urls are HTML landing pages; skip
                out_file = None
            else:
                row["pdf_path"] = out_file
        else:
            row["pdf_path"] = None
        rows.append(row)
    df = pd.DataFrame(rows)
    # order columns
    cols = ["title","abstract","journal","year","doi","authors","affiliations","cited_by_count","open_access_status","is_oa","pdf_path","source"]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]
    return df

# -----------------------
# PDF integrity check and update excel (delete broken pdfs and remove rows)
# -----------------------
def pdf_check_and_cleanup(excel_path: str, pdf_base_dir: str, backup: bool = True, verbose: bool = True) -> Tuple[int,int]:
    """
    Check each pdf path listed in the excel file; if pdf missing or invalid remove the row and delete file reference.
    Returns (checked_count, removed_count). Updates excel in place (back up original).
    """

    if not os.path.exists(excel_path):
        if verbose:
            print("[PDF-Check] excel not found:", excel_path)
        return 0,0
    df = pd.read_excel(excel_path)
    if df.empty:
        return 0,0
    checked = 0
    removed = 0
    to_keep = []
    for idx, row in df.iterrows():
        pdfp = row.get("pdf_path")
        checked += 1
        if not pdfp or not isinstance(pdfp, str) or not os.path.exists(pdfp):
            # remove row
            removed += 1
            if verbose:
                print(f"[PDF-Check] missing: {pdfp} (will remove row)")
            continue
        ok = check_pdf_valid(pdfp)
        if not ok:
            removed += 1
            try:
                os.remove(pdfp)
            except Exception:
                pass
            if verbose:
                print(f"[PDF-Check] invalid/corrupt: {pdfp} (removed)")
            continue
        to_keep.append(row)
    if backup:
        bak = excel_path + ".bak." + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            shutil.copy2(excel_path, bak)
            if verbose:
                print("[PDF-Check] backed up original excel to:", bak)
        except Exception:
            pass
    # write updated excel
    if to_keep:
        new_df = pd.DataFrame(to_keep)
    else:
        new_df = pd.DataFrame(columns=df.columns)
    new_df.to_excel(excel_path, index=False)
    if verbose:
        print(f"[PDF-Check] completed: {checked} checked, {removed} removed.")
    return checked, removed

# -----------------------
# Main orchestration
# -----------------------
def main():
    # ========== Parameters from config file ==========
    # Keywords from config (or fallback to default)
    keywords_raw = get_config("search.keywords", "")
    if keywords_raw:
        # Clean up YAML multiline string (remove extra newlines)
        keywords = " ".join(keywords_raw.strip().split("\n"))
    else:
        # Fallback default keywords
        keywords = '("nano fluorescent probe") OR ("nanoscale fluorescent probe") OR ("fluorescent nanoprobe")'
    
    # Email for Unpaywall and Crossref polite requests
    mailto = get_config("api_keys.contact_email", DEFAULT_EMAIL)

    # Output directory & excel path
    out_base = get_config("output.base_dir", "outputs/literature")
    excel_filename = get_config("output.excel_filename", "nano_fluorescent_probes.xlsx")
    excel_path = os.path.join(out_base, excel_filename)

    # Sources and order
    sources_order = get_config("search.sources_order", ["openalex", "wos", "semantic_scholar", "pubmed", "arxiv", "crossref"])

    # Limits
    max_results_per_clause = get_config("search.max_results_per_clause", 200)
    max_total = get_config("search.max_total", 10000)
    max_clauses = get_config("search.max_clauses", 50)
    year_from = get_config("search.year_from", 2000)
    year_to = get_config("search.year_to", 2030)

    # Incremental mode
    incremental = get_config("runtime.incremental", True)
    verbose = get_config("runtime.verbose", True)
    
    ensure_dir(out_base)
    existing_dois = set()
    if incremental and os.path.exists(excel_path):
        try:
            df_exist = pd.read_excel(excel_path)
            for d in df_exist.get("doi", []) or []:
                if pd.isna(d):
                    continue
                existing_dois.add(str(d).strip())
            print(f"[Incremental] Loaded {len(existing_dois)} existing DOIs from {excel_path}, will skip them.")
        except Exception as e:
            print("[Incremental] could not read existing excel:", e)

    # split keywords into clauses
    clauses = split_keywords_into_clauses(keywords, max_clauses=max_clauses)
    print(f"[Split] derived {len(clauses)} clauses from keywords.")
    for i, c in enumerate(clauses, start=1):
        print(f"[Clause {i}] {c}")

    # gather works
    all_works = []
    for idx, clause in enumerate(clauses, start=1):
        print(f"[RunClause] ({idx}/{len(clauses)}) starting clause: {clause}")
        works = run_clause_search(clause, sources_order=sources_order, max_per_clause=max_results_per_clause, mailto=mailto, verbose=True, year_from=year_from, year_to=year_to, semantic_api_key=SEMANTIC_SCHOLAR_API_KEY)
        print(f"[RunClause] clause {idx} returned {len(works)} raw works")
        all_works.extend(works)
        # small break if huge
        if len(all_works) >= max_total:
            print("[Main] reached max_total cap, stopping clause loop")
            break

    print(f"[Merge] merging and deduplicating...")
    merged = merge_and_dedupe(all_works, max_total=max_total)
    print(f"[Merge] merged total: {len(merged)} (capped to {max_total})")

    # Fill missing DOIs via Crossref
    print("[Fill] filling missing DOIs via Crossref title lookup...")
    merged = fill_missing_dois(merged, mailto=mailto, verbose=True)

    # remove works whose DOI already in incremental set
    if incremental and existing_dois:
        kept = []
        skipped = 0
        for w in merged:
            d = doi_normalize(w.get("doi") or "")
            if d and d in existing_dois:
                skipped += 1
                continue
            kept.append(w)
        print(f"[Incremental] Skipped {skipped} already-existing DOIs; {len(kept)} new works remain.")
        merged = kept

    # assemble and attempt download of OA PDFs
    print("[Download] attempting to download OA PDFs and assembling table...")
    df_final = download_pdfs_and_assemble(merged, out_base, mailto=mailto, email=mailto, verbose=True)

    # merge with existing excel (incremental)
    if incremental and os.path.exists(excel_path):
        try:
            old = pd.read_excel(excel_path)
            combined = pd.concat([old, df_final], ignore_index=True)
            # dedupe by DOI when possible, otherwise by title
            combined["doi_norm"] = combined["doi"].apply(lambda x: doi_normalize(str(x)) if pd.notna(x) else None)
            combined = combined.sort_values(["year", "journal", "title"], ascending=[False, True, True])
            combined = combined.drop_duplicates(subset=["doi_norm","title"], keep="first")
            combined = combined.drop(columns=["doi_norm"], errors="ignore")
            final_df = combined
        except Exception:
            final_df = df_final
    else:
        final_df = df_final

    # write excel
    ensure_dir(out_base)
    final_df.to_excel(excel_path, index=False)
    print(f"[OK] XLSX written: {excel_path} ({len(final_df)} rows)")

    # PDF check and cleanup
    print("[PDF-Check] verifying downloaded PDFs...")

    checked, removed = pdf_check_and_cleanup(excel_path, os.path.join(out_base, "PDF_download"), backup=True, verbose=True)

    # summary
    n_oa = int(final_df["is_oa"].fillna(False).sum()) if "is_oa" in final_df.columns else 0
    print(f"[Summary] total exported: {len(final_df)}; OA: {n_oa}; PDFs attempted: {final_df['pdf_path'].notna().sum() if 'pdf_path' in final_df.columns else 0}")
    print("[Done]")

if __name__ == "__main__":
    main()
