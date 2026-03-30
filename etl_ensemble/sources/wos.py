"""Web of Science (WoS / Clarivate) search module."""

import re
from typing import List, Optional

import requests

import logging
logger = logging.getLogger(__name__)

from .base import rate_limit_source

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WOS_BASE = "https://api.clarivate.com/apis/wos-starter/v1/documents"
WOS_API_KEY: str = ""
_WOS_DB_CACHE: Optional[str] = None


def configure(api_key: str = "") -> None:
    """Set the WoS API key.

    Args:
        api_key: Clarivate WoS API key.
    """
    global WOS_API_KEY
    WOS_API_KEY = api_key


def choose_best_wos_db(verbose: bool = True) -> Optional[str]:
    """Try candidate db values to find one that returns results.

    Args:
        verbose: Log diagnostic messages.

    Returns:
        Best db identifier or None if no key is set.
    """
    global _WOS_DB_CACHE
    if _WOS_DB_CACHE:
        return _WOS_DB_CACHE

    if not WOS_API_KEY:
        if verbose:
            logger.info("[WoS] WOS_API_KEY not set; skipping WoS.")
        return None

    headers = {"X-ApiKey": WOS_API_KEY, "Accept": "application/json"}
    candidates = ["WOS", "MEDLINE", "BIOSIS", "WOK", "WOSCC"]
    test_q = 'TS=("nano fluorescent probe")'
    for db in candidates:
        params = {"q": test_q, "db": db, "limit": 1, "page": 1}
        try:
            rate_limit_source('wos')
            r = requests.get(WOS_BASE, headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                try:
                    js = r.json()
                    total = (js.get("metadata") or {}).get("total")
                    if total and int(total) > 0:
                        if verbose:
                            logger.info("[WoS-Test][%s] HTTP 200 total=%s", db, total)
                        _WOS_DB_CACHE = db
                        return _WOS_DB_CACHE
                except Exception:
                    pass
        except Exception:
            pass
    _WOS_DB_CACHE = "WOS"
    return _WOS_DB_CACHE


def search_wos_clause(
    clause: str,
    max_results: int = 100,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    verbose: bool = True,
) -> List[dict]:
    """Search WoS with a single clause using TS= prefix and pagination.

    Args:
        clause: Query clause.
        max_results: Max results to return.
        year_from: Start year filter.
        year_to: End year filter.
        verbose: Log progress.

    Returns:
        List of work dicts with keys: source, doi, display_name, journal, etc.
    """
    if not WOS_API_KEY:
        if verbose:
            logger.info("[WoS] skip: no API key")
        return []

    db = choose_best_wos_db(verbose=verbose)
    if not db:
        if verbose:
            logger.info("[WoS] choose_best_wos_db returned None; skipping WoS")
        return []

    headers = {"X-ApiKey": WOS_API_KEY, "Accept": "application/json"}
    q_body = clause
    if not re.search(r'\bTS=', q_body):
        q_body = f"TS=({q_body})"
    if year_from and year_to:
        q_body = f"({q_body}) AND PY={year_from}-{year_to}"
    elif year_from:
        q_body = f"({q_body}) AND PY>={year_from}"
    elif year_to:
        q_body = f"({q_body}) AND PY<={year_to}"

    results: List[dict] = []
    page = 1
    page_size = 50

    while len(results) < max_results:
        params = {"q": q_body, "db": db, "limit": page_size, "page": page}
        try:
            rate_limit_source('wos')
            r = requests.get(WOS_BASE, headers=headers, params=params, timeout=30)
            if r.status_code != 200:
                if verbose:
                    logger.warning("[WoS] HTTP %d: %s", r.status_code, r.text[:300])
                break
            js = r.json()
        except Exception as e:
            if verbose:
                logger.warning("[WoS] request exception: %s", e)
            break

        hits = js.get("hits") or []
        if not hits:
            break

        for item in hits:
            source = item.get("source") or {}
            title = item.get("title") or item.get("titleRaw") or None
            doi = item.get("doi")
            if not doi:
                for ident in item.get("identifiers") or []:
                    if isinstance(ident, dict) and ident.get("type", "").lower() == "doi":
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
                "cited_by_count": cited,
            })
            if len(results) >= max_results:
                break
        page += 1

    return results[:max_results]
