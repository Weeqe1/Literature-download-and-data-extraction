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
import asyncio
import aiohttp
import concurrent.futures # Async IO for downloads
import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import quote_plus
import pandas as pd
from tqdm import tqdm
from dateutil import parser as dtparser
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential, retry_if_exception_type

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
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", get_config("api_keys.openalex", ""))
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", get_config("api_keys.semantic_scholar", ""))
DEFAULT_EMAIL = get_config("api_keys.contact_email", "wangqi@ahut.edu.cn")

# HTTP session
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "harvest_literature/1.0 (mailto:%s)" % DEFAULT_EMAIL})
REQS_PER_SECOND = get_config("runtime.requests_per_second", 4)
MIN_SLEEP = 1.0 / max(1, REQS_PER_SECOND)

def rate_limit():
    time.sleep(MIN_SLEEP)

# Semantic Scholar requirement: <= 1 request/sec (across its endpoints).
_S2_LAST_REQUEST_TS = 0.0

def rate_limit_semantic_scholar(min_interval_sec: float = 1.05) -> None:
    global _S2_LAST_REQUEST_TS
    now = time.time()
    wait = (_S2_LAST_REQUEST_TS + min_interval_sec) - now
    if wait > 0:
        time.sleep(wait)
    _S2_LAST_REQUEST_TS = time.time()

# per-source runtime stats for concise debug logging
_LAST_SOURCE_STATS: Dict[str, Dict[str, int]] = {}

def set_source_stats(source: str, scanned_raw: int, returned: int) -> None:
    _LAST_SOURCE_STATS[source] = {
        "scanned_raw": max(0, int(scanned_raw)),
        "returned": max(0, int(returned)),
    }

def get_source_stats(source: str) -> Dict[str, int]:
    return _LAST_SOURCE_STATS.get(source, {})

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


def normalize_text(text: str) -> str:
    """
    Normalize text for robust phrase matching.
    - Convert to lowercase
    - Remove hyphens (nano-probe -> nanoprobe)
    - Remove extra whitespace
    - Keep alphanumeric + spaces only
    """
    if not text:
        return ""
    # lowercase
    t = text.lower()
    # remove hyphens and underscores
    t = t.replace("-", "").replace("_", "").replace("/", " ")
    # collapse multiple spaces
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def parse_clause_units(clause: str) -> Tuple[List[str], List[str], bool]:
    """
    Parse a boolean clause into positive units, negative units and whether AND exists.
    Units are phrases/terms used for local relevance matching.
    """
    if not clause:
        return [], [], False

    s = clause.strip()
    has_and = bool(re.search(r"\bAND\b", s, flags=re.I))

    # Extract NOT units first
    neg_quoted = re.findall(r'\bNOT\s+"([^"]+)"', s, flags=re.I)
    neg_bare = re.findall(r'\bNOT\s+([A-Za-z0-9_\-]+)', s, flags=re.I)
    negatives = [x.strip().lower() for x in (neg_quoted + neg_bare) if x and x.strip()]

    # Remove NOT fragments to avoid counting them as positives
    s_pos = re.sub(r'\bNOT\s+"[^"]+"', ' ', s, flags=re.I)
    s_pos = re.sub(r'\bNOT\s+[A-Za-z0-9_\-]+', ' ', s_pos, flags=re.I)

    # Prefer quoted phrases as units
    quoted = [q.strip().lower() for q in re.findall(r'"([^"]+)"', s_pos) if q and q.strip()]
    if quoted:
        positives = quoted
    else:
        # Fallback to bare tokens
        tokens = re.split(r'\s+', re.sub(r'[()"]', ' ', s_pos))
        positives = []
        for t in tokens:
            tl = t.strip().lower()
            if not tl:
                continue
            if tl in ("and", "or", "not", "ts="):
                continue
            if len(re.sub(r'[^a-z0-9]', '', tl)) < 3:
                continue
            positives.append(tl)

    # Deduplicate while preserving order
    def _uniq(seq: List[str]) -> List[str]:
        seen = set()
        out = []
        for it in seq:
            if it not in seen:
                seen.add(it)
                out.append(it)
        return out

    return _uniq(positives), _uniq(negatives), has_and


def openalex_abstract_to_text(inv_idx: Any) -> str:
    """Rebuild plain abstract text from OpenAlex abstract_inverted_index."""
    if not isinstance(inv_idx, dict):
        return ""
    pairs = []
    for token, positions in inv_idx.items():
        if not isinstance(positions, list):
            continue
        for p in positions:
            try:
                pairs.append((int(p), token))
            except Exception:
                continue
    if not pairs:
        return ""
    pairs.sort(key=lambda x: x[0])
    return " ".join(t for _, t in pairs)


def build_source_query(source: str, clause: str, title_only: bool = False) -> str:
    """
    Build source-specific query text from one clause.
    Keep semantics close to clause while adapting to endpoint syntax.
    """
    positives, negatives, has_and = parse_clause_units(clause)
    if not positives:
        return clause.strip()

    if source == "wos":
        body = " AND ".join([f'"{p}"' for p in positives]) if has_and else " OR ".join([f'"{p}"' for p in positives])
        if negatives:
            body += " NOT " + " NOT ".join([f'"{n}"' for n in negatives])
        return body

    if source == "pubmed":
        field = "[Title]" if title_only else "[Title/Abstract]"
        joiner = " AND " if has_and else " OR "
        body = joiner.join([f'"{p}"{field}' for p in positives])
        if negatives:
            body += " NOT " + " NOT ".join([f'"{n}"{field}' for n in negatives])
        return body

    if source == "arxiv":
        if title_only:
            return " OR ".join([f'ti:\"{p}\"' for p in positives])
        return " OR ".join([f'all:\"{p}\"' for p in positives])

    if source == "crossref":
        # Crossref: use phrase-based queries for better precision
        # For AND clauses, phrase queries naturally narrow results
        # For OR clauses, use all as separate phrases
        if has_and:
            # Use AND to connect phrases for precision
            return " AND ".join([f'"{p}"' for p in positives])
        else:
            # OR mode: use phrase search
            return " ".join([f'"{p}"' for p in positives])

    if source == "semantic_scholar":
        # Semantic Scholar /paper/search expects plain text query (no special boolean syntax).
        return " ".join(positives)

    if source == "openalex":
        # OpenAlex search is free text; avoid strict quoted-phrase query that can under-recall.
        # Use plain token sequence to improve recall, local matcher will keep precision.
        return " ".join(positives)

    return clause.strip()


def match_work_against_clause(work: Dict[str, Any], clause: str, title_only: bool = False) -> bool:
    """Local boolean matching to filter out non-target records from broad API results.
    Uses normalized matching for robustness (handles hyphens, case, whitespace).
    """
    positives, negatives, has_and = parse_clause_units(clause)
    if not positives:
        return True

    title = (work.get("display_name") or work.get("title") or "")
    abstract = (work.get("abstract_text") or work.get("abstract") or "")
    if not abstract and work.get("abstract_inverted_index"):
        abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))

    text = title if title_only else (title + " " + abstract)
    
    # Normalize for matching
    normalized_text = normalize_text(text)
    normalized_positives = [normalize_text(p) for p in positives]
    normalized_negatives = [normalize_text(n) for n in negatives]

    # negatives first
    for n in normalized_negatives:
        if n and n in normalized_text:
            return False

    if has_and:
        return all(p in normalized_text for p in normalized_positives)
    return any(p in normalized_text for p in normalized_positives)


def match_work_against_clause_with_reason(work: Dict[str, Any], clause: str, title_only: bool = False, match_strictness: float = 1.0) -> Tuple[bool, str]:
    """Return (matched, reason) for local boolean filtering.
    Uses normalized matching for robustness (handles hyphens, case, whitespace).
    
    Args:
        match_strictness (0.0-1.0): Controls term matching requirement.
            1.0 = all terms must match (strict, default)
            0.5 = 50% of terms must match
            0.0 = any single term matches (lenient)
    """
    positives, negatives, has_and = parse_clause_units(clause)
    if not positives:
        return True, "no_positive_units"

    title = (work.get("display_name") or work.get("title") or "")
    abstract = (work.get("abstract_text") or work.get("abstract") or "")
    if not abstract and work.get("abstract_inverted_index"):
        abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))

    text = title if title_only else (title + " " + abstract)
    
    # Normalize for matching
    normalized_text = normalize_text(text)
    normalized_positives = [normalize_text(p) for p in positives]
    normalized_negatives = [normalize_text(n) for n in negatives]

    hit_negative = [n for n in negatives if normalized_text.find(normalize_text(n)) >= 0]
    if hit_negative:
        return False, "hit_negative:" + ",".join(hit_negative[:3])

    # Apply match_strictness to AND/OR matching
    if has_and:
        matched_positives = sum(1 for p in normalized_positives if p in normalized_text)
        required_matches = max(1, int(len(normalized_positives) * match_strictness))
        if matched_positives >= required_matches:
            return True, f"matched_and_{matched_positives}/{len(normalized_positives)}"
        else:
            missing = [positives[i] for i in range(len(positives)) if normalized_positives[i] not in normalized_text][:3]
            return False, f"missing_and_terms_{matched_positives}/{required_matches}:" + ",".join(missing)
    else:
        matched_positives = sum(1 for p in normalized_positives if p in normalized_text)
        required_matches = max(1, int(len(normalized_positives) * match_strictness))
        if matched_positives >= required_matches:
            return True, f"matched_or_{matched_positives}/{len(normalized_positives)}"
        return False, f"missing_or_terms_{matched_positives}/{required_matches}"

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
OPENALEX_TIMEOUT_SEC = int(get_config("runtime.openalex_timeout_sec", 45) or 45)
OPENALEX_RETRY_ATTEMPTS = int(get_config("runtime.openalex_retry_attempts", 4) or 4)
OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED = bool(get_config("runtime.openalex_disable_on_budget_exhausted", True))
_OPENALEX_BUDGET_EXHAUSTED = False
_OPENALEX_BUDGET_WARNED = False

@retry(stop=stop_after_attempt(max(1, OPENALEX_RETRY_ATTEMPTS)), wait=wait_exponential(min=1, max=8), retry=retry_if_exception_type((requests.RequestException,)))
def openalex_get(params: dict):
    global _OPENALEX_BUDGET_EXHAUSTED
    if OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED and _OPENALEX_BUDGET_EXHAUSTED:
        raise requests.RequestException("OpenAlex disabled for this run: budget exhausted (HTTP 429 Insufficient budget)")

    def _mark_budget_exhausted_from_text(msg: str) -> None:
        global _OPENALEX_BUDGET_EXHAUSTED
        if not OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED:
            return
        low = (msg or "").lower()
        if "openalex http 429" in low and "insufficient budget" in low:
            _OPENALEX_BUDGET_EXHAUSTED = True

    req_params = dict(params or {})
    if OPENALEX_API_KEY and "api_key" not in req_params:
        req_params["api_key"] = OPENALEX_API_KEY

    rate_limit()
    try:
        r = SESSION.get(OPENALEX_BASE, params=req_params, timeout=OPENALEX_TIMEOUT_SEC)
        if r.status_code != 200:
            msg = f"OpenAlex HTTP {r.status_code}: {r.text[:300]}"
            _mark_budget_exhausted_from_text(msg)
            raise requests.RequestException(msg)
        return r.json()
    except requests.RequestException as sess_err:
        # Fallback channel: bypass pooled session and issue a direct request.
        rate_limit()
        try:
            r2 = requests.get(
                OPENALEX_BASE,
                params=req_params,
                timeout=OPENALEX_TIMEOUT_SEC,
                headers={"User-Agent": SESSION.headers.get("User-Agent", "harvest_literature/1.0")},
            )
            if r2.status_code != 200:
                msg2 = f"OpenAlex HTTP {r2.status_code}: {r2.text[:300]}"
                _mark_budget_exhausted_from_text(msg2)
                raise requests.RequestException(msg2)
            return r2.json()
        except requests.RequestException as direct_err:
            raise requests.RequestException(
                f"OpenAlex session+direct failed | session={type(sess_err).__name__}: {str(sess_err)[:160]} | "
                f"direct={type(direct_err).__name__}: {str(direct_err)[:160]}"
            )

def search_openalex_clause(clause: str, max_results: int = 2000, title_only: bool = False, year_from: Optional[int] = None, year_to: Optional[int] = None, mailto: Optional[str] = None) -> List[dict]:
    """
    Search OpenAlex for a clause. If title_only True, use title.search; otherwise use default.search (title+abstract).
    Returns list of works (raw dicts).
    """
    global _OPENALEX_BUDGET_WARNED

    if OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED and _OPENALEX_BUDGET_EXHAUSTED:
        if not _OPENALEX_BUDGET_WARNED:
            print("[OpenAlex] skipped: budget exhausted (HTTP 429 Insufficient budget). Will retry next run.")
            _OPENALEX_BUDGET_WARNED = True
        set_source_stats("openalex", scanned_raw=0, returned=0)
        return []

    results = []
    scanned_raw = 0
    per_page = 50
    min_per_page = 10
    page = 1
    error_logged = False
    consecutive_failures = 0

    positives, negatives, has_and = parse_clause_units(clause)
    clause_lc = clause.lower()
    has_boolean_ops = bool(re.search(r"\b(and|or|not)\b", clause_lc, flags=re.I))
    # For plain multi-word text query (e.g. "nano fluorescent probe"), require phrase/all tokens.
    simple_space_query = (not has_boolean_ops) and (len(positives) > 1)
    phrase_norm = normalize_text(clause.strip().strip('"'))

    def _prefilter_openalex(work: Dict[str, Any]) -> bool:
        title = work.get("display_name") or work.get("title") or ""
        abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))
        hay = normalize_text(title) if title_only else normalize_text((title or "") + " " + (abstract or ""))

        if simple_space_query and phrase_norm:
            # strict phrase match first; fallback to all-token match for minor formatting variance.
            if phrase_norm in hay:
                return True
            token_match = all(normalize_text(p) in hay for p in positives)
            return token_match

        norm_pos = [normalize_text(p) for p in positives]
        norm_neg = [normalize_text(n) for n in negatives]
        for n in norm_neg:
            if n and n in hay:
                return False
        if not norm_pos:
            return True
        if has_and:
            return all(p in hay for p in norm_pos)
        return any(p in hay for p in norm_pos)

    def _fmt_openalex_error(err: Exception) -> str:
        base = err
        if isinstance(err, RetryError):
            try:
                inner = err.last_attempt.exception()
                if inner is not None:
                    base = inner
            except Exception:
                pass
        return f"{type(base).__name__}: {str(base)[:240]}"
    
    params = {"per-page": per_page, "page": page, "select": ",".join([
        "id","doi","display_name","title","abstract_inverted_index","publication_year","publication_date",
        "best_oa_location","open_access","authorships","type","language","is_paratext","cited_by_count"
    ])}
    if mailto:
        params["mailto"] = mailto
    
    # Use search param (OpenAlex API uses 'search' parameter)
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
        js = None
        last_err = None
        for _ in range(3):
            try:
                js = openalex_get(params)
                break
            except Exception as e:
                last_err = e
                time.sleep(1.0)
        if js is None:
            consecutive_failures += 1
            # expose failures for diagnosis but avoid log flooding
            if not error_logged:
                print(f"[OpenAlex] request failed: {_fmt_openalex_error(last_err) if last_err else 'unknown'}")
                error_logged = True
            # On repeated failures, progressively reduce page size to ease server/network pressure.
            per_page = max(min_per_page, int(per_page * 0.5))
            params["per-page"] = per_page
            time.sleep(min(6.0, 1.5 * consecutive_failures))
            # If we already have partial results, keep them and stop this clause.
            if results:
                break
            # For cold-start failures, allow more retries with reduced page size.
            if consecutive_failures >= 4:
                break
            continue
        if consecutive_failures > 0:
            # Recover page size gradually after successful responses.
            per_page = min(50, per_page + 10)
            params["per-page"] = per_page
        consecutive_failures = 0
        works = js.get("results", [])
        if not works:
            break
        scanned_raw += len(works)
        for w in works:
            if not _prefilter_openalex(w):
                continue
            results.append(w)
            if len(results) >= max_results:
                break
        page += 1
        # Guardrails against deep noisy pagination.
        if page > 80:
            break
        if scanned_raw >= max(2000, max_results * 2) and len(results) < max(100, int(max_results * 0.05)):
            break
    final_results = results[:max_results]
    set_source_stats("openalex", scanned_raw=scanned_raw, returned=len(final_results))
    return final_results

# -----------------------
# WoS search (Clarivate APIs)
# -----------------------
WOS_BASE = "https://api.clarivate.com/apis/wos-starter/v1/documents"
_WOS_DB_CACHE: Optional[str] = None

def choose_best_wos_db(verbose: bool = True) -> Optional[str]:
    """
    Try some db values to determine a db that returns search results (heuristic).
    """
    global _WOS_DB_CACHE
    if _WOS_DB_CACHE:
        return _WOS_DB_CACHE

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
                        _WOS_DB_CACHE = db
                        return _WOS_DB_CACHE
                except Exception:
                    pass
            else:
                # continue trying other dbs
                pass
        except Exception:
            pass
    _WOS_DB_CACHE = "WOS"
    return _WOS_DB_CACHE  # fallback

def search_wos_clause(clause: str, max_results: int = 100, year_from: Optional[int] = None, year_to: Optional[int] = None, verbose: bool = True) -> List[dict]:
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
    return results[:max_results]

# -----------------------
# Semantic Scholar
# -----------------------
def search_semantic_scholar_clause(
    clause: str,
    max_results: int = 100,
    title_only: bool = False,
    api_key: Optional[str] = None,
    verbose: bool = True,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[dict]:
    """
    Query Semantic Scholar Graph API. Use conservative fields to avoid HTTP 400.
    """
    if api_key is None:
        api_key = SEMANTIC_SCHOLAR_API_KEY

    # /paper/search requires plain text and docs note hyphenated terms may fail.
    q = (clause or "").strip()
    q = q.replace('"', ' ')
    q = re.sub(r'\b(AND|OR|NOT)\b', ' ', q, flags=re.I)
    q = q.replace('-', ' ')
    q = re.sub(r'\s+', ' ', q).strip()
    if not q:
        q = (clause or "").strip()

    base = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,abstract,year,venue,authors,externalIds,isOpenAccess,openAccessPdf"
    out = []
    scanned_raw = 0
    offset = 0
    # Relevance search endpoint can return at most 1000 ranked results.
    target = max(0, min(max_results, 1000))
    page_size = min(100, max(1, target))
    use_key = bool(api_key)

    last_status = None
    last_body = ""
    last_exc = None

    while len(out) < target and offset < 1000:
        params = {
            "query": q,
            "offset": offset,
            "limit": min(page_size, target - len(out)),
            "fields": fields,
        }
        if year_from and year_to:
            params["year"] = f"{year_from}-{year_to}"
        elif year_from:
            params["year"] = f"{year_from}-"
        elif year_to:
            params["year"] = f"-{year_to}"

        attempts = 0
        backoff = 1.0
        minimal_fields_used = False
        page_ok = False
        while attempts < 5:
            headers = {"User-Agent": "pdf_download_harvester/1.0"}
            if use_key and api_key:
                headers["x-api-key"] = api_key
            try:
                rate_limit()
                rate_limit_semantic_scholar()
                r = requests.get(base, params=params, headers=headers, timeout=25)
            except Exception as e:
                last_exc = e
                attempts += 1
                time.sleep(backoff)
                backoff *= 2
                continue

            last_status = r.status_code
            last_body = r.text[:300] if getattr(r, "text", None) else ""

            if r.status_code == 200:
                js = r.json()
                items = js.get("data") or []
                scanned_raw += len(items)
                if not items:
                    page_ok = True
                    offset = 1000
                    break
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
                    if len(out) >= target:
                        break

                next_offset = js.get("next")
                if isinstance(next_offset, int) and next_offset > offset:
                    offset = next_offset
                else:
                    offset += len(items)
                page_ok = True
                break

            if r.status_code in (429, 500, 502, 503, 504):
                attempts += 1
                time.sleep(backoff)
                backoff *= 2
                continue

            if r.status_code == 400 and not minimal_fields_used:
                params["fields"] = "title,year,authors,externalIds"
                minimal_fields_used = True
                attempts += 1
                continue

            if r.status_code in (401, 403) and use_key:
                # Fallback to unauthenticated request once if key is rejected.
                use_key = False
                attempts += 1
                continue

            # Other 4xx: stop this source for current clause.
            attempts = 999

        if not page_ok:
            break

    set_source_stats("semantic_scholar", scanned_raw=scanned_raw, returned=len(out))
    if not out and verbose:
        if last_exc is not None and last_status is None:
            print(f"[Semantic Scholar] persistent failures; last exception: {str(last_exc)[:180]}")
        else:
            print(f"[Semantic Scholar] persistent failures; last status={last_status}, body={last_body}")
    return out

# -----------------------
# PubMed (Entrez eutils)
# -----------------------
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
def search_pubmed_clause(clause: str, max_results: int = 150, title_only: bool = False, email: Optional[str] = None) -> List[dict]:
    """
    Use esearch to get ids, then efetch to get summary fields via retmode=xml.
    Clause should be adapted to PubMed syntax; if clause contains quotes treat them as phrase.
    Implements pagination to fetch beyond the 200 limit per request.
    """
    if email is None:
        email = DEFAULT_EMAIL
    
    term = clause
    
    import xml.etree.ElementTree as ET
    
    # Step 1: Get total count and all IDs with pagination
    all_ids = []
    retstart = 0
    batch_size = 500  # PubMed allows up to 500 per request
    
    while len(all_ids) < max_results:
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": min(batch_size, max_results - len(all_ids)),
            "retstart": retstart,
            "retmode": "xml",
            "email": email
        }
        
        try:
            rate_limit()
            r = requests.get(PUBMED_ESEARCH, params=params, timeout=25)
            if r.status_code != 200:
                break
            
            es = ET.fromstring(r.text)
            ids = [idn.text for idn in es.findall(".//IdList/Id")]
            if not ids:
                break
            
            all_ids.extend(ids)
            
            # Check if we've reached the end
            count = int(es.findtext(".//Count") or 0)
            if len(all_ids) >= count:
                break
            
            retstart += len(ids)
            
        except Exception as e:
            break
    
    if not all_ids:
        return []
    
    # Step 2: Fetch details in batches
    out = []
    batch_size_fetch = 200  # efetch limit
    
    for i in range(0, len(all_ids), batch_size_fetch):
        batch_ids = all_ids[i:i + batch_size_fetch]
        ids_str = ",".join(batch_ids)
        
        params2 = {"db": "pubmed", "id": ids_str, "retmode": "xml"}
        
        try:
            rate_limit()
            r2 = requests.get(PUBMED_EFETCH, params=params2, timeout=30)
            if r2.status_code != 200:
                continue
            
            root = ET.fromstring(r2.text)
            
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
                        "source": "pubmed",
                        "doi": doi,
                        "display_name": title,
                        "abstract_text": abstract,
                        "publication_year": int(year) if year and year.isdigit() else None,
                        "journal": journal,
                        "authors_list": authors
                    })
                    
                    if len(out) >= max_results:
                        break
                except Exception:
                    continue
        except Exception:
            continue
        
        if len(out) >= max_results:
            break
    
    return out[:max_results]

# -----------------------
# arXiv
# -----------------------
ARXIV_API = "http://export.arxiv.org/api/query"
def search_arxiv_clause(clause: str, max_results: int = 100, title_only: bool = False) -> List[dict]:
    # Clause is already source-adapted in run_clause_search.
    q = clause
    params = {"search_query": q, "start":0, "max_results": min(max_results, 200)}
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
def search_crossref_clause(
    clause: str,
    max_results: int = 150,
    mailto: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    title_only: bool = False,
    min_score_ratio: float = 0.25,
    max_scan_raw: int = 1500,
) -> List[dict]:
    """Search Crossref with field-aware query strategy and pagination.

    title_only=True  -> use query.title for precision.
    title_only=False -> use query.bibliographic for broader recall.
    Also applies type/year filters and stops early when relevance drops sharply.
    """
    if max_results <= 0:
        return []
    
    out = []
    offset = 0
    rows_per_page = 500
    top_score: Optional[float] = None
    scanned_raw = 0
    page_count = 0

    # Internal pre-filter to avoid returning broad noisy pages to outer pipeline.
    positives, negatives, has_and = parse_clause_units(clause)

    def _prefilter(title_txt: str, abstract_txt: str) -> bool:
        if not positives:
            return True
        t = normalize_text(title_txt or "")
        a = normalize_text(abstract_txt or "")
        hay = t if title_only else (t + " " + a).strip()
        pos = [normalize_text(x) for x in positives]
        neg = [normalize_text(x) for x in negatives]
        for n in neg:
            if n and n in hay:
                return False
        if has_and:
            return all(p in hay for p in pos)
        return any(p in hay for p in pos)
    
    # Build date filter
    filters = ["type:journal-article"]
    if year_from:
        filters.append(f"from-pub-date:{year_from}")
    if year_to:
        filters.append(f"until-pub-date:{year_to}")
    
    while len(out) < max_results:
        page_count += 1
        # Calculate rows for this request
        rows = min(rows_per_page, max_results - len(out))
        
        params = {
            "rows": rows,
            "offset": offset,
            "filter": ",".join(filters),
            "select": "DOI,title,abstract,issued,container-title,author,score",
        }
        if title_only:
            params["query.title"] = clause
        else:
            params["query.bibliographic"] = clause
        if mailto:
            params["mailto"] = mailto
        
        try:
            rate_limit()
            r = requests.get(CROSSREF_API, params=params, timeout=30)
            if r.status_code != 200:
                break
            
            js = r.json()
            items = js.get("message", {}).get("items", [])
            if not items:
                break
            scanned_raw += len(items)
            
            low_relevance_count = 0
            for it in items:
                score = it.get("score")
                if isinstance(score, (int, float)):
                    if top_score is None:
                        top_score = float(score)
                    elif top_score > 0 and float(score) < top_score * min_score_ratio:
                        low_relevance_count += 1
                doi = it.get("DOI")
                title = (it.get("title") or [None])[0]
                abstract = it.get("abstract")
                clean_abstract = re.sub(r'<[^>]+>', '', abstract) if abstract else None
                if not _prefilter(title or "", clean_abstract or ""):
                    continue
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
                    "abstract_text": clean_abstract,
                    "publication_year": year,
                    "journal": journal,
                    "authors_list": authors
                })
            
            # Update offset for next page
            offset += len(items)
            
            # If we got fewer items than requested, we've reached the end
            if len(items) < rows:
                break
            # If most of this page is already low relevance, stop pagination early.
            if len(items) > 0 and low_relevance_count >= int(len(items) * 0.8):
                break
            # Guardrail: if scanned many raw records with very low yield, stop early.
            if scanned_raw >= max_scan_raw and len(out) < max(100, int(max_results * 0.05)):
                break
            # Guardrail: avoid deep pagination loops on extremely broad clauses.
            if page_count >= 20:
                break
                
        except Exception:
            break
    
    final_out = out[:max_results]
    set_source_stats("crossref", scanned_raw=scanned_raw, returned=len(final_out))
    return final_out

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
# Helper: download file (with retry and cleanup)
# -----------------------
def _cleanup_partial_file(out_path: str):
    """Remove a partially downloaded file if it exists."""
    try:
        if os.path.exists(out_path):
            os.remove(out_path)
    except OSError:
        pass

def download_file(url: str, out_path: str, timeout: int = 60, max_retries: int = 3, verbose: bool = False) -> bool:
    """Download a file from URL with retry logic and partial file cleanup.
    
    Args:
        url: URL to download
        out_path: Local file path to save to
        timeout: Request timeout in seconds
        max_retries: Maximum number of retry attempts
        verbose: Print retry messages
        
    Returns:
        True if download succeeded, False otherwise
    """
    if not url:
        return False
    
    ensure_dir(os.path.dirname(out_path))
    
    for attempt in range(1, max_retries + 1):
        try:
            rate_limit()
            with requests.get(url, stream=True, timeout=timeout) as r:
                # 4xx/5xx errors: don't retry client errors (404, 403, etc.)
                if r.status_code == 404 or r.status_code == 403:
                    if verbose:
                        print(f"  [Download] HTTP {r.status_code} for {url[:80]}...")
                    return False
                if r.status_code != 200:
                    if verbose:
                        print(f"  [Download] HTTP {r.status_code} (attempt {attempt}/{max_retries})")
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)  # exponential backoff
                        continue
                    return False
                
                # Stream download to file
                with open(out_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
                
                # Verify file is not empty
                if os.path.getsize(out_path) < 100:
                    if verbose:
                        print(f"  [Download] Downloaded file too small ({os.path.getsize(out_path)} bytes), discarding")
                    _cleanup_partial_file(out_path)
                    if attempt < max_retries:
                        time.sleep(2 ** attempt)
                        continue
                    return False
                
                return True
                
        except requests.exceptions.ConnectionError as e:
            if verbose:
                print(f"  [Download] Connection error (attempt {attempt}/{max_retries}): {e}")
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # exponential backoff
                continue
            
        except requests.exceptions.Timeout as e:
            if verbose:
                print(f"  [Download] Timeout (attempt {attempt}/{max_retries}): {e}")
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"  [Download] Request error (attempt {attempt}/{max_retries}): {e}")
            _cleanup_partial_file(out_path)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            
        except OSError as e:
            if verbose:
                print(f"  [Download] File system error: {e}")
            _cleanup_partial_file(out_path)
            return False  # disk errors don't retry
    
    # All retries exhausted
    _cleanup_partial_file(out_path)
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


def export_rejected_audit(audit_rows: List[Dict[str, Any]], out_path: str, verbose: bool = True) -> None:
    """Export locally filtered-out samples to an audit excel file."""
    if not audit_rows:
        if verbose:
            print("[Audit] no filtered-out samples to export")
        return
    try:
        df = pd.DataFrame(audit_rows)
        df.to_excel(out_path, index=False)
        if verbose:
            print(f"[Audit] exported filtered-out samples: {len(df)} -> {out_path}")
    except Exception as e:
        print(f"[Audit] failed to export audit file: {e}")

# -----------------------
# High-level flow: for each clause, run searches (order configurable)
# two rounds: title-only then title+abstract; accumulate results
# -----------------------
def run_clause_search(clause: str, sources_order: List[str], max_per_clause: int = 200, mailto: Optional[str] = None, verbose: bool = True, year_from: Optional[int] = None, year_to: Optional[int] = None, semantic_api_key: Optional[str] = None, audit_rejections: Optional[List[Dict[str, Any]]] = None, audit_limit: int = 2000, match_strictness: float = 0.7) -> List[dict]:
    """
    Run the configured sources for a single clause, in two rounds (title-only then title+abstract).
    Each source function is called with a clause string adapted for that source as needed.
    Returns raw works list.
    """
    collected = []
    # clamp to [0.0, 1.0] to avoid accidental invalid config values
    try:
        match_strictness = float(match_strictness)
    except Exception:
        match_strictness = 0.7
    match_strictness = max(0.0, min(1.0, match_strictness))

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
        return build_source_query(source, c, title_only=title_only_flag)

    # wrappers map
    def call_source(src: str, q: str, title_only_flag: bool):
        try:
            if src == "openalex":
                return search_openalex_clause(q, max_results=max_per_clause, title_only=title_only_flag, year_from=year_from, year_to=year_to, mailto=mailto)
            if src == "wos":
                return search_wos_clause(q, max_results=max_per_clause, year_from=year_from, year_to=year_to)
            if src == "semantic_scholar":
                return search_semantic_scholar_clause(
                    q,
                    max_results=max_per_clause,
                    title_only=title_only_flag,
                    api_key=semantic_api_key,
                    year_from=year_from,
                    year_to=year_to,
                )
            if src == "pubmed":
                return search_pubmed_clause(q, max_results=max_per_clause, title_only=title_only_flag, email=mailto)
            if src == "arxiv":
                return search_arxiv_clause(q, max_results=max_per_clause, title_only=title_only_flag)
            if src == "crossref":
                return search_crossref_clause(
                    q,
                    max_results=max_per_clause,
                    mailto=mailto,
                    year_from=year_from,
                    year_to=year_to,
                    title_only=title_only_flag,
                )
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
                # Uniform local boolean filtering to remove off-target results.
                filtered = []
                for it in items:
                    ok, reason = match_work_against_clause_with_reason(it, clause, title_only=title_only, match_strictness=match_strictness)
                    if ok:
                        filtered.append(it)
                    else:
                        if audit_rejections is not None and len(audit_rejections) < max(0, audit_limit):
                            audit_rejections.append({
                                "clause": clause,
                                "source": src,
                                "round": which,
                                "reason": reason,
                                "title": it.get("display_name") or it.get("title") or "",
                                "doi": doi_normalize(it.get("doi") or ""),
                                "year": it.get("publication_year") or it.get("year") or None,
                                "journal": it.get("journal") or extract_journal_from_work(it) or ""
                            })
                if verbose:
                    print(f"[{src}] returned {len(items)} items for clause, kept {len(filtered)} after local clause match")
                    stats = get_source_stats(src)
                    scanned_raw = stats.get("scanned_raw", len(items))
                    returned_count = stats.get("returned", len(items))
                    print(f"[{src}] dbg {scanned_raw} -> {returned_count} -> {len(filtered)}")
                collected.extend(filtered)
            else:
                if verbose:
                    print(f"[{src}] returned 0 items for clause")
                    stats = get_source_stats(src)
                    scanned_raw = stats.get("scanned_raw", 0)
                    returned_count = stats.get("returned", 0)
                    print(f"[{src}] dbg {scanned_raw} -> {returned_count} -> 0")
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
# Download OA PDFs and assemble final DataFrame (with checkpoint + concurrency)
# -----------------------

def _check_disk_space(path: str, min_mb: int = 500) -> bool:
    """Check if there's enough disk space at the given path."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        free_mb = free / (1024 * 1024)
        return free_mb >= min_mb
    except OSError:
        return True  # can't check, assume OK

def _resolve_pdf_url(row: dict, doi: str, email: str) -> Tuple[Optional[str], bool]:
    """Try to find a downloadable PDF URL for a work."""
    pdf_url = row.get("pdf_url")
    is_oa = False
    
    if pdf_url:
        is_oa = True
        return pdf_url, is_oa
    
    if doi:
        pdf_url, is_oa = get_unpaywall_pdf_by_doi(doi, email)
    
    return pdf_url, is_oa

def _download_single_work(args: Tuple) -> Dict[str, Any]:
    """Download a single work's PDF. Designed for use with ThreadPoolExecutor."""
    w, pdf_dir, email = args
    row = work_to_row(w)
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

def _save_checkpoint(rows: List[Dict], cols: List[str], excel_path: str):
    """Save current progress as a checkpoint Excel file."""
    try:
        df = pd.DataFrame(rows)
        for c in cols:
            if c not in df.columns:
                df[c] = None
        df = df[cols]
        df.to_excel(excel_path, index=False)
    except OSError as e:
        print(f"  [Checkpoint] Failed to save: {e}")

def download_pdfs_and_assemble(
    works: List[dict],
    out_dir: str,
    mailto: Optional[str] = None,
    email: Optional[str] = None,
    max_workers: int = 4,
    checkpoint_interval: int = 100,
    checkpoint_path: Optional[str] = None,
    verbose: bool = True
) -> pd.DataFrame:
    """Download OA PDFs and assemble final DataFrame.
    
    Features:
    - Concurrent downloading with ThreadPoolExecutor
    - Periodic checkpoint saves to Excel
    - Disk space monitoring
    - Retry with exponential backoff on download failures
    
    Args:
        works: List of work dicts to process
        out_dir: Output directory for Excel and PDFs
        mailto: Email for Unpaywall/Crossref polite requests
        email: Email for Unpaywall
        max_workers: Number of concurrent download threads (1 = sequential)
        checkpoint_interval: Save checkpoint every N downloads
        checkpoint_path: Path for checkpoint Excel (default: out_dir/_checkpoint.xlsx)
        verbose: Print progress messages
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
        "pdf_path", "source"
    ]
    
    # Load existing checkpoint to resume
    existing_dois = {}
    if os.path.exists(checkpoint_path):
        try:
            df_ckpt = pd.read_excel(checkpoint_path)
            for _, row in df_ckpt.iterrows():
                d = doi_normalize(str(row.get("doi", "")) if pd.notna(row.get("doi")) else "")
                if d:
                    existing_dois[d] = True
            if verbose:
                print(f"  [Resume] Loaded {len(existing_dois)} DOIs from checkpoint")
        except Exception:
            pass
    
    # Filter out already-processed works
    works_to_process = []
    pre_rows = []
    for w in works:
        doi = doi_normalize(w.get("doi") or "")
        if doi and doi in existing_dois:
            # Already processed, skip
            continue
        works_to_process.append(w)
    
    if verbose:
        print(f"  [Download] {len(works_to_process)} works to process (of {len(works)} total)")
    
    if not works_to_process:
        # Everything already processed, load checkpoint
        if os.path.exists(checkpoint_path):
            df = pd.read_excel(checkpoint_path)
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            return df[cols]
        return pd.DataFrame(columns=cols)
    
    # Check disk space before starting
    if not _check_disk_space(pdf_dir, min_mb=500):
        print("  [Warning] Low disk space (<500MB free). Downloads may fail.")
    
    rows = []
    download_args = [(w, pdf_dir, email_addr) for w in works_to_process]
    
    if max_workers <= 1:
        # Sequential download with checkpoint
        for i, args in enumerate(tqdm(download_args, desc="[Download] Sequential"), 1):
            row = _download_single_work(args)
            rows.append(row)
            
            # Periodic checkpoint
            if i % checkpoint_interval == 0:
                if verbose:
                    print(f"  [Checkpoint] Saving progress ({i}/{len(download_args)})...")
                all_rows = rows  # in sequential mode, rows is complete so far
                _save_checkpoint(all_rows, cols, checkpoint_path)
            
            # Periodic disk check
            if i % 500 == 0:
                if not _check_disk_space(pdf_dir, min_mb=200):
                    print(f"  [Warning] Disk space critically low after {i} downloads. Stopping.")
                    break
    else:
        # Concurrent download
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
                            print(f"  [Download] Worker error: {e}")
                    
                    pbar.update(1)
                    
                    # Periodic checkpoint
                    total_done = completed + failed
                    if total_done % checkpoint_interval == 0 and total_done > 0:
                        _save_checkpoint(rows, cols, checkpoint_path)
                        if verbose:
                            pbar.set_postfix(ok=completed, fail=failed)
                    
                    # Periodic disk check
                    if total_done % 500 == 0:
                        if not _check_disk_space(pdf_dir, min_mb=200):
                            print(f"  [Warning] Disk space critically low. Cancelling remaining downloads.")
                            for f in future_to_idx:
                                f.cancel()
                            break
        
        if verbose:
            print(f"  [Download] Complete: {completed} succeeded, {failed} failed")
    
    # Save final checkpoint
    _save_checkpoint(rows, cols, checkpoint_path)
    
    # Build final DataFrame
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]
    return df

# -----------------------
# PDF integrity check and update excel (delete broken pdfs and remove rows)
# -----------------------
def pdf_check_and_cleanup(
    excel_path: str,
    pdf_base_dir: str,
    backup: bool = True,
    verbose: bool = True,
    log_each: bool = False,
    remove_invalid_rows: bool = False,
) -> Tuple[int,int]:
    """
    Check each pdf path listed in the excel file.
    - remove_invalid_rows=True: remove rows with missing/invalid PDFs.
    - remove_invalid_rows=False: keep rows and clear invalid pdf_path.
    Returns (checked_count, invalid_count). Updates excel in place (back up original).
    """

    if not os.path.exists(excel_path):
        if verbose:
            print("[PDF-Check] excel not found:", excel_path)
        return 0,0
    df = pd.read_excel(excel_path)
    if df.empty:
        return 0,0
    checked = 0
    invalid = 0
    dropped_rows = 0
    to_keep = []
    for idx, row in df.iterrows():
        pdfp = row.get("pdf_path")
        if not pdfp or not isinstance(pdfp, str) or not pdfp.strip():
            # No PDF was downloaded for this row; keep metadata and skip integrity check.
            row["pdf_valid"] = False
            to_keep.append(row)
            continue

        checked += 1
        if not os.path.exists(pdfp):
            invalid += 1
            if verbose and log_each:
                print(f"[PDF-Check] missing: {pdfp}")
            if remove_invalid_rows:
                dropped_rows += 1
                continue
            row["pdf_path"] = None
            row["pdf_valid"] = False
            to_keep.append(row)
            continue

        ok = check_pdf_valid(pdfp)
        if not ok:
            invalid += 1
            try:
                os.remove(pdfp)
            except Exception:
                pass
            if verbose and log_each:
                print(f"[PDF-Check] invalid/corrupt: {pdfp}")
            if remove_invalid_rows:
                dropped_rows += 1
                continue
            row["pdf_path"] = None
            row["pdf_valid"] = False
            to_keep.append(row)
            continue
        row["pdf_valid"] = True
        to_keep.append(row)
    if backup:
        # 原始文件保持原名，检查后的文件添加_check后缀
        base_name = excel_path.rsplit('.xlsx', 1)[0]
        checked_path = base_name + '_check.xlsx'
    else:
        checked_path = excel_path
    # write updated excel (checked version)
    if to_keep:
        new_df = pd.DataFrame(to_keep)
    else:
        new_df = pd.DataFrame(columns=df.columns)
    new_df.to_excel(checked_path, index=False)
    if verbose:
        print(f"[PDF-Check] completed: checked_pdfs={checked}, invalid_pdfs={invalid}, dropped_rows={dropped_rows}.")
    return checked, invalid

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
    audit_filename = get_config("output.audit_rejected_filename", "filtered_out_audit.xlsx")
    audit_limit = get_config("output.audit_rejected_limit", 2000)
    audit_path = os.path.join(out_base, audit_filename)

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
    match_strictness = get_config("runtime.match_strictness", 0.7)
    
    ensure_dir(out_base)
    existing_dois = set()
    if incremental and os.path.exists(excel_path):
        try:
            df_exist = pd.read_excel(excel_path)
            doi_values = df_exist["doi"].tolist() if "doi" in df_exist.columns else []
            for d in doi_values:
                if pd.isna(d):
                    continue
                ds = str(d).strip()
                if ds:
                    existing_dois.add(ds)
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
    rejected_audit = []
    for idx, clause in enumerate(clauses, start=1):
        print(f"[RunClause] ({idx}/{len(clauses)}) starting clause: {clause}")
        works = run_clause_search(
            clause,
            sources_order=sources_order,
            max_per_clause=max_results_per_clause,
            mailto=mailto,
            verbose=True,
            year_from=year_from,
            year_to=year_to,
            semantic_api_key=SEMANTIC_SCHOLAR_API_KEY,
            audit_rejections=rejected_audit,
            audit_limit=audit_limit,
            match_strictness=match_strictness,
        )
        print(f"[RunClause] clause {idx} returned {len(works)} raw works")
        all_works.extend(works)
        # small break if huge
        if len(all_works) >= max_total:
            print("[Main] reached max_total cap, stopping clause loop")
            break

    # Export filtered-out samples for audit
    export_rejected_audit(rejected_audit, audit_path, verbose=True)

    print(f"[Merge] merging and deduplicating...")
    merged = merge_and_dedupe(all_works, max_total=max_total)
    print(f"[Merge] merged total: {len(merged)} (capped to {max_total})")

    # Fill missing DOIs via Crossref
    print("[Fill] filling missing DOIs via Crossref title lookup...")
    merged = fill_missing_dois(merged, mailto=mailto, verbose=True)

    # Quality control: validate, clean, and filter literature
    print("[Quality] validating and cleaning metadata...")
    try:
        from quality_control import LiteratureQualityController
        qc = LiteratureQualityController()
        merged = qc.validate_and_clean_metadata(merged)
        print(f"[Quality] cleaned {len(merged)} works")
        
        # Quality filtering (if enabled)
        quality_enabled = get_config("quality.enabled", False)
        if quality_enabled:
            print("[Quality] filtering literature by relevance and completeness...")
            min_relevance = get_config("quality.min_relevance", 0.05)
            min_completeness = get_config("quality.min_completeness", 0.1)
            min_overall = get_config("quality.min_overall", 0.1)
            
            filtered_works, stats = qc.filter_literature(
                merged,
                min_relevance=min_relevance,
                min_completeness=min_completeness,
                min_overall=min_overall
            )
            
            print(f"[Quality] Filter results:")
            print(f"  Input: {stats['total_input']}")
            print(f"  Passed: {stats['passed_filter']}")
            print(f"  Rejected by relevance: {stats['rejected_by_relevance']}")
            print(f"  Rejected by completeness: {stats['rejected_by_completeness']}")
            print(f"  Rejected by overall: {stats['rejected_by_overall']}")
            print(f"  Quality: High={stats['high_quality_count']}, Medium={stats['medium_quality_count']}, Low={stats['low_quality_count']}")
            
            merged = filtered_works
        else:
            print("[Quality] quality filtering disabled (set quality.enabled=true to enable)")
    except ImportError:
        print("[Warning] quality_control module not found, skipping quality filtering")

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
    
    # Download configuration
    max_workers = get_config("runtime.max_concurrent_downloads", 4)
    checkpoint_interval = get_config("runtime.checkpoint_interval", 100)
    checkpoint_path = os.path.join(out_base, "_checkpoint.xlsx")
    
    df_final = download_pdfs_and_assemble(
        merged, out_base, mailto=mailto, email=mailto,
        max_workers=max_workers,
        checkpoint_interval=checkpoint_interval,
        checkpoint_path=checkpoint_path,
        verbose=verbose
    )

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

    pdf_check_log_each = get_config("runtime.pdf_check_log_each", False)
    pdf_check_remove_invalid_rows = get_config("runtime.pdf_check_remove_invalid_rows", False)
    checked, removed = pdf_check_and_cleanup(
        excel_path,
        os.path.join(out_base, "PDF_download"),
        backup=True,
        verbose=verbose,
        log_each=pdf_check_log_each,
        remove_invalid_rows=pdf_check_remove_invalid_rows,
    )

    # summary
    n_oa = int(final_df["is_oa"].fillna(False).sum()) if "is_oa" in final_df.columns else 0
    print(f"[Summary] total exported: {len(final_df)}; OA: {n_oa}; PDFs attempted: {final_df['pdf_path'].notna().sum() if 'pdf_path' in final_df.columns else 0}")
    print("[Done]")

if __name__ == "__main__":
    main()
