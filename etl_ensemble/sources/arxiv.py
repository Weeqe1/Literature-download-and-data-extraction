"""arXiv API search module."""

from typing import List

import requests
from dateutil import parser as dtparser

import logging
logger = logging.getLogger(__name__)

from .base import rate_limit

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ARXIV_API = "http://export.arxiv.org/api/query"


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
    params = {"search_query": q, "start": 0, "max_results": min(max_results, 200)}
    try:
        rate_limit()
        r = requests.get(ARXIV_API, params=params, timeout=30)
        if r.status_code != 200:
            return []

        import xml.etree.ElementTree as ET
        root = ET.fromstring(r.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        out: List[dict] = []
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
        return out
    except Exception:
        return []
