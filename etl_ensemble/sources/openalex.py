"""OpenAlex search module.

Searches the OpenAlex /works API with pagination, budget tracking,
and local boolean pre-filtering.
"""

import os
import re
import time
from typing import List, Dict, Any, Optional

import requests
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import logging
logger = logging.getLogger(__name__)

from .base import (
    rate_limit,
    parse_clause_units,
    normalize_text,
    set_source_stats,
    openalex_abstract_to_text,
)

# ---------------------------------------------------------------------------
# Configurable constants (set via configure())
# ---------------------------------------------------------------------------
OPENALEX_BASE = "https://api.openalex.org/works"
OPENALEX_API_KEY: str = ""
OPENALEX_TIMEOUT_SEC: int = 45
OPENALEX_RETRY_ATTEMPTS: int = 4
OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED: bool = True

# Runtime state
_OPENALEX_BUDGET_EXHAUSTED: bool = False
_OPENALEX_BUDGET_WARNED: bool = False

# Shared HTTP session (set externally)
SESSION: Optional[requests.Session] = None


def configure(
    api_key: str = "",
    timeout_sec: int = 45,
    retry_attempts: int = 4,
    disable_on_budget_exhausted: bool = True,
    session: Optional[requests.Session] = None,
) -> None:
    """Configure OpenAlex module parameters.

    Args:
        api_key: OpenAlex API key.
        timeout_sec: Request timeout in seconds.
        retry_attempts: Number of retry attempts per request.
        disable_on_budget_exhausted: Stop searching after HTTP 429 budget error.
        session: Shared requests.Session instance.
    """
    global OPENALEX_API_KEY, OPENALEX_TIMEOUT_SEC, OPENALEX_RETRY_ATTEMPTS
    global OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED, SESSION
    OPENALEX_API_KEY = api_key
    OPENALEX_TIMEOUT_SEC = timeout_sec
    OPENALEX_RETRY_ATTEMPTS = retry_attempts
    OPENALEX_DISABLE_ON_BUDGET_EXHAUSTED = disable_on_budget_exhausted
    if session is not None:
        SESSION = session


@retry(
    stop=stop_after_attempt(max(1, OPENALEX_RETRY_ATTEMPTS)),
    wait=wait_exponential(min=1, max=8),
    retry=retry_if_exception_type((requests.RequestException,)),
)
def openalex_get(params: dict) -> dict:
    """Make a request to the OpenAlex API with retry and fallback.

    When the polite pool (API key) budget is exhausted (HTTP 429), automatically
    falls back to the public pool (no API key) which has no daily budget limit.

    Args:
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        requests.RequestException: On persistent failure.
    """
    global _OPENALEX_BUDGET_EXHAUSTED, _OPENALEX_BUDGET_WARNED

    def _mark_budget_exhausted_from_text(msg: str) -> None:
        global _OPENALEX_BUDGET_EXHAUSTED
        low = (msg or "").lower()
        if "insufficient budget" in low or ("429" in msg and "budget" in low):
            _OPENALEX_BUDGET_EXHAUSTED = True

    req_params = dict(params or {})

    # If polite pool budget exhausted, remove API key to fall back to public pool
    if _OPENALEX_BUDGET_EXHAUSTED:
        req_params.pop("api_key", None)
        if not _OPENALEX_BUDGET_WARNED:
            logger.info("[OpenAlex] Budget exhausted, falling back to public pool (10 req/s limit)")
            _OPENALEX_BUDGET_WARNED = True
    elif OPENALEX_API_KEY and "api_key" not in req_params:
        req_params["api_key"] = OPENALEX_API_KEY

    sess = SESSION or requests.Session()

    rate_limit_source('openalex')
    try:
        r = sess.get(OPENALEX_BASE, params=req_params, timeout=OPENALEX_TIMEOUT_SEC)
        if r.status_code == 429 and "insufficient budget" in r.text.lower():
            # Polite pool budget exhausted → retry without API key
            _mark_budget_exhausted_from_text(f"OpenAlex HTTP 429: {r.text[:300]}")
            req_params.pop("api_key", None)
            rate_limit_source('openalex')
            r = sess.get(OPENALEX_BASE, params=req_params, timeout=OPENALEX_TIMEOUT_SEC)
        if r.status_code != 200:
            msg = f"OpenAlex HTTP {r.status_code}: {r.text[:300]}"
            _mark_budget_exhausted_from_text(msg)
            raise requests.RequestException(msg)
        return r.json()
    except requests.RequestException as sess_err:
        if "budget" in str(sess_err).lower():
            raise
        rate_limit_source('openalex')
        try:
            public_params = dict(params or {})
            public_params.pop("api_key", None)
            r2 = requests.get(
                OPENALEX_BASE,
                params=public_params,
                timeout=OPENALEX_TIMEOUT_SEC,
                headers={"User-Agent": sess.headers.get("User-Agent", "harvest_literature/1.0")},
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


def search_openalex_clause(
    clause: str,
    max_results: int = 2000,
    title_only: bool = False,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    mailto: Optional[str] = None,
) -> List[dict]:
    """Search OpenAlex for a clause with pagination and pre-filtering.

    Args:
        clause: Search clause string.
        max_results: Maximum results to return.
        title_only: If True, search title only.
        year_from: Start year filter.
        year_to: End year filter.
        mailto: Email for polite pool.

    Returns:
        List of work dicts.
    """
    global _OPENALEX_BUDGET_WARNED

    # Budget exhaustion is now handled by openalex_get with automatic fallback to public pool
    # No need to skip - just let it run with reduced rate

    results: List[dict] = []
    scanned_raw = 0
    per_page = 50
    min_per_page = 10
    page = 1
    error_logged = False
    consecutive_failures = 0

    positives, negatives, has_and = parse_clause_units(clause)
    clause_lc = clause.lower()
    has_boolean_ops = bool(re.search(r"\b(and|or|not)\b", clause_lc, flags=re.I))
    simple_space_query = (not has_boolean_ops) and (len(positives) > 1)
    phrase_norm = normalize_text(clause.strip().strip('"'))

    def _prefilter_openalex(work: Dict[str, Any]) -> bool:
        title = work.get("display_name") or work.get("title") or ""
        abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))
        hay = normalize_text(title) if title_only else normalize_text((title or "") + " " + (abstract or ""))

        if simple_space_query and phrase_norm:
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

    params = {
        "per-page": per_page,
        "page": page,
        "select": ",".join([
            "id", "doi", "display_name", "title", "abstract_inverted_index",
            "publication_year", "publication_date", "best_oa_location",
            "open_access", "authorships", "type", "language", "is_paratext", "cited_by_count",
        ]),
    }
    if mailto:
        params["mailto"] = mailto

    params["search"] = clause
    if year_from and year_to:
        params["filter"] = f"publication_year:{year_from}-{year_to}"
    elif year_from:
        params["filter"] = f"publication_year:>={year_from}"
    elif year_to:
        params["filter"] = f"publication_year:<={year_to}"

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
            if not error_logged:
                logger.warning("[OpenAlex] request failed: %s", _fmt_openalex_error(last_err) if last_err else "unknown")
                error_logged = True
            per_page = max(min_per_page, int(per_page * 0.5))
            params["per-page"] = per_page
            time.sleep(min(6.0, 1.5 * consecutive_failures))
            if results:
                break
            if consecutive_failures >= 4:
                break
            continue
        if consecutive_failures > 0:
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
        if page > 80:
            break
        if scanned_raw >= max(2000, max_results * 2) and len(results) < max(100, int(max_results * 0.05)):
            break

    final_results = results[:max_results]
    set_source_stats("openalex", scanned_raw=scanned_raw, returned=len(final_results))
    return final_results
