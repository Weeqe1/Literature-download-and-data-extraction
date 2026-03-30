"""Semantic Scholar Graph API search module."""

import re
import time
from typing import List, Optional

import requests

import logging
logger = logging.getLogger(__name__)

from .base import rate_limit, rate_limit_semantic_scholar, safe_get, set_source_stats

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SEMANTIC_SCHOLAR_API_KEY: str = ""


def configure(api_key: str = "") -> None:
    """Set the Semantic Scholar API key.

    Args:
        api_key: Semantic Scholar API key.
    """
    global SEMANTIC_SCHOLAR_API_KEY
    SEMANTIC_SCHOLAR_API_KEY = api_key


def search_semantic_scholar_clause(
    clause: str,
    max_results: int = 100,
    title_only: bool = False,
    api_key: Optional[str] = None,
    verbose: bool = True,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> List[dict]:
    """Query Semantic Scholar Graph API for papers.

    Args:
        clause: Search query string.
        max_results: Maximum results (capped at 1000).
        title_only: Unused (Semantic Scholar does not support title-only search).
        api_key: Override API key.
        verbose: Log warnings on failure.
        year_from: Start year filter.
        year_to: End year filter.

    Returns:
        List of work dicts.
    """
    if api_key is None:
        api_key = SEMANTIC_SCHOLAR_API_KEY

    q = (clause or "").strip()
    q = q.replace('"', ' ')
    q = re.sub(r'\b(AND|OR|NOT)\b', ' ', q, flags=re.I)
    q = q.replace('-', ' ')
    q = re.sub(r'\s+', ' ', q).strip()
    if not q:
        q = (clause or "").strip()

    base = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "title,abstract,year,venue,authors,externalIds,isOpenAccess,openAccessPdf"
    out: List[dict] = []
    scanned_raw = 0
    offset = 0
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
                        "oa_url": safe_get(it, "openAccessPdf", "url"),
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
                use_key = False
                attempts += 1
                continue

            attempts = 999  # stop this source

        if not page_ok:
            break

    set_source_stats("semantic_scholar", scanned_raw=scanned_raw, returned=len(out))
    if not out and verbose:
        if last_exc is not None and last_status is None:
            logger.warning("[Semantic Scholar] persistent failures; last exception: %s", str(last_exc)[:180])
        else:
            logger.warning("[Semantic Scholar] persistent failures; last status=%s, body=%s", last_status, last_body)
    return out
