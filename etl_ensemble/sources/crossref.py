"""Crossref REST API search module."""

import re
from typing import List, Optional, Tuple

import requests

import logging
logger = logging.getLogger(__name__)

from .base import rate_limit, parse_clause_units, normalize_text, set_source_stats, doi_normalize

# ---------------------------------------------------------------------------
# Optional fuzzy matching
# ---------------------------------------------------------------------------
try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CROSSREF_API = "https://api.crossref.org/works"
UNPAYWALL_API = "https://api.unpaywall.org/v2/"


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

    Args:
        clause: Query string.
        max_results: Max results to return.
        mailto: Email for polite pool.
        year_from: Start year filter.
        year_to: End year filter.
        title_only: Use query.title instead of query.bibliographic.
        min_score_ratio: Minimum relevance score ratio vs top result.
        max_scan_raw: Maximum raw records to scan before stopping.

    Returns:
        List of work dicts.
    """
    if max_results <= 0:
        return []

    out: List[dict] = []
    offset = 0
    rows_per_page = 500
    top_score: Optional[float] = None
    scanned_raw = 0
    page_count = 0

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

    filters = ["type:journal-article"]
    if year_from:
        filters.append(f"from-pub-date:{year_from}")
    if year_to:
        filters.append(f"until-pub-date:{year_to}")

    while len(out) < max_results:
        page_count += 1
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
                    authors.append(" ".join([a.get("given", ""), a.get("family", "")]).strip())
                out.append({
                    "source": "crossref",
                    "doi": doi,
                    "display_name": title,
                    "abstract_text": clean_abstract,
                    "publication_year": year,
                    "journal": journal,
                    "authors_list": authors,
                })

            offset += len(items)
            if len(items) < rows:
                break
            if len(items) > 0 and low_relevance_count >= int(len(items) * 0.8):
                break
            if scanned_raw >= max_scan_raw and len(out) < max(100, int(max_results * 0.05)):
                break
            if page_count >= 20:
                break
        except Exception:
            break

    final_out = out[:max_results]
    set_source_stats("crossref", scanned_raw=scanned_raw, returned=len(final_out))
    return final_out


def crossref_find_doi_by_title(title: str, mailto: Optional[str] = None) -> Optional[str]:
    """Look up a DOI by title using Crossref, with fuzzy matching.

    Args:
        title: Paper title.
        mailto: Email for polite pool.

    Returns:
        Best-matching DOI or None.
    """
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


def get_unpaywall_pdf_by_doi(doi: str, email: str) -> Tuple[Optional[str], bool]:
    """Look up open-access PDF URL via Unpaywall.

    Args:
        doi: DOI string.
        email: Contact email for polite pool.

    Returns:
        Tuple of (pdf_url, is_oa).
    """
    if not doi:
        return None, False
    url = f"{UNPAYWALL_API}{requests.utils.quote(doi, safe='')}"
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
