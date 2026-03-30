"""arXiv API search module.

Note: arXiv API enforces strict rate limits (~1 request per 3 seconds).
HTTP 429 responses are handled with exponential backoff.
"""

import time
from typing import List, Optional

import requests
from dateutil import parser as dtparser

import logging
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ARXIV_API = "https://export.arxiv.org/api/query"
_ARXIV_LAST_TS: float = 0.0
_ARXIV_MIN_INTERVAL: float = 3.0  # arXiv recommends 3s between requests


def _arxiv_rate_limit() -> None:
    """arXiv-specific rate limiter: enforce >= 3s between requests."""
    global _ARXIV_LAST_TS
    elapsed = time.monotonic() - _ARXIV_LAST_TS
    if elapsed < _ARXIV_MIN_INTERVAL:
        time.sleep(_ARXIV_MIN_INTERVAL - elapsed)
    _ARXIV_LAST_TS = time.monotonic()


def _arxiv_get(params: dict, timeout: int = 120, max_retries: int = 3) -> Optional[requests.Response]:
    """Make an arXiv API request with 429 retry and backoff.

    Args:
        params: Query parameters.
        timeout: Request timeout in seconds.
        max_retries: Number of retry attempts on 429.

    Returns:
        Response object or None on failure.
    """
    for attempt in range(1, max_retries + 1):
        _arxiv_rate_limit()
        try:
            r = requests.get(ARXIV_API, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 429:
                wait = 5 * attempt  # 5s, 10s, 15s
                logger.warning("[arXiv] HTTP 429 (rate limited), waiting %ds (attempt %d/%d)", wait, attempt, max_retries)
                time.sleep(wait)
                continue
            logger.warning("[arXiv] HTTP %d (attempt %d/%d)", r.status_code, attempt, max_retries)
            return None
        except requests.exceptions.Timeout:
            logger.warning("[arXiv] timeout (attempt %d/%d)", attempt, max_retries)
            if attempt < max_retries:
                time.sleep(5)
        except Exception as e:
            logger.warning("[arXiv] request error: %s", e)
            return None
    return None


def search_arxiv_clause(
    clause: str,
    max_results: int = 100,
    title_only: bool = False,
) -> List[dict]:
    """Search arXiv API and parse Atom XML results.

    Args:
        clause: arXiv-formatted query string (e.g. 'all:"nano probe"').
        max_results: Maximum number of results (capped at 200 per request).
        title_only: Unused (query should already specify field).

    Returns:
        List of work dicts.
    """
    q = clause
    page_size = min(max_results, 200)
    out: List[dict] = []

    start = 0
    while start < max_results:
        this_batch = min(page_size, max_results - start)
        params = {"search_query": q, "start": start, "max_results": this_batch}

        r = _arxiv_get(params)
        if r is None:
            break

        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(r.text)
        except ET.ParseError:
            break

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            break

        for e in entries:
            title = e.findtext("atom:title", default="", namespaces=ns)
            summary = e.findtext("atom:summary", default="", namespaces=ns)
            pub = e.findtext("atom:published", default="", namespaces=ns)
            year = None
            try:
                if pub:
                    year = dtparser.parse(pub).year
            except Exception:
                year = None
            out.append({
                "source": "arxiv",
                "doi": None,
                "display_name": title.strip(),
                "abstract_text": summary.strip(),
                "publication_year": year,
                "journal": "arXiv",
                "authors_list": [
                    a.findtext("atom:name", default="", namespaces=ns)
                    for a in e.findall("atom:author", ns)
                ],
            })

        start += len(entries)
        if len(entries) < this_batch:
            break

    return out
