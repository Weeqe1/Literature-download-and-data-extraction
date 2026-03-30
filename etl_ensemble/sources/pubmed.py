"""PubMed (NCBI Entrez E-utilities) search module."""

import re
from typing import List, Optional

import requests

import logging
logger = logging.getLogger(__name__)

from .base import rate_limit_source

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
DEFAULT_EMAIL: str = "wangqi@ahut.edu.cn"


def configure(email: str = "") -> None:
    """Set the contact email for PubMed polite requests.

    Args:
        email: Contact email address.
    """
    global DEFAULT_EMAIL
    if email:
        DEFAULT_EMAIL = email


def search_pubmed_clause(
    clause: str,
    max_results: int = 150,
    title_only: bool = False,
    email: Optional[str] = None,
) -> List[dict]:
    """Search PubMed using esearch + efetch with XML parsing.

    Args:
        clause: PubMed-formatted query string.
        max_results: Maximum number of results.
        title_only: Unused (query should already be field-tagged).
        email: Contact email for NCBI.

    Returns:
        List of work dicts.
    """
    import xml.etree.ElementTree as ET

    if email is None:
        email = DEFAULT_EMAIL

    term = clause

    # Step 1: Get all IDs with pagination
    all_ids: List[str] = []
    retstart = 0
    batch_size = 500

    while len(all_ids) < max_results:
        params = {
            "db": "pubmed",
            "term": term,
            "retmax": min(batch_size, max_results - len(all_ids)),
            "retstart": retstart,
            "retmode": "xml",
            "email": email,
        }
        try:
            rate_limit_source('pubmed')
            r = requests.get(PUBMED_ESEARCH, params=params, timeout=25)
            if r.status_code != 200:
                break
            es = ET.fromstring(r.text)
            ids = [idn.text for idn in es.findall(".//IdList/Id")]
            if not ids:
                break
            all_ids.extend(ids)
            count = int(es.findtext(".//Count") or 0)
            if len(all_ids) >= count:
                break
            retstart += len(ids)
        except Exception:
            break

    if not all_ids:
        return []

    # Step 2: Fetch details in batches
    out: List[dict] = []
    batch_size_fetch = 200

    for i in range(0, len(all_ids), batch_size_fetch):
        batch_ids = all_ids[i:i + batch_size_fetch]
        ids_str = ",".join(batch_ids)
        params2 = {"db": "pubmed", "id": ids_str, "retmode": "xml"}

        try:
            rate_limit_source('pubmed')
            r2 = requests.get(PUBMED_EFETCH, params=params2, timeout=30)
            if r2.status_code != 200:
                continue
            root = ET.fromstring(r2.text)

            for article in root.findall(".//PubmedArticle"):
                try:
                    title = article.findtext(".//ArticleTitle")
                    abstract = " ".join([
                        t.text.strip() for t in article.findall(".//AbstractText")
                        if t is not None and t.text
                    ])
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
                        "authors_list": authors,
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
