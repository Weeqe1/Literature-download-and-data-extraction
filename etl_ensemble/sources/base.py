"""Base utilities for literature harvester: text processing, matching, rate limiting.

Provides common functions shared across all source search modules.
"""

import os
import re
import time
from typing import List, Dict, Any, Optional, Tuple

import logging
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiting - per-source throttling to avoid IP bans
# ---------------------------------------------------------------------------
_REQS_PER_SECOND: float = 0.3
_MIN_SLEEP: float = 1.0 / max(0.1, _REQS_PER_SECOND)

# Per-source minimum interval (seconds) between consecutive requests
# These are conservative values to be polite to free APIs
_SOURCE_INTERVALS: Dict[str, float] = {
    "openalex": 2.0,
    "wos": 2.0,
    "semantic_scholar": 3.0,
    "pubmed": 1.0,
    "arxiv": 5.0,        # arXiv is very strict about rate limits
    "crossref": 2.0,
}
_SOURCE_LAST_TS: Dict[str, float] = {}

# Per-source 429 cooldown tracking
_SOURCE_COOLDOWN_UNTIL: Dict[str, float] = {}


def configure_rate_limit(reqs_per_second: float) -> None:
    """Set the global rate limit for API requests.

    Args:
        reqs_per_second: Maximum requests per second.
    """
    global _REQS_PER_SECOND, _MIN_SLEEP
    _REQS_PER_SECOND = max(0.1, reqs_per_second)
    _MIN_SLEEP = 1.0 / _REQS_PER_SECOND


def rate_limit() -> None:
    """Sleep for the configured minimum interval between requests."""
    time.sleep(_MIN_SLEEP)


def rate_limit_source(source: str, min_interval: Optional[float] = None) -> None:
    """Enforce per-source rate limit with 429 cooldown check.

    Args:
        source: Source name (openalex, wos, semantic_scholar, etc.).
        min_interval: Override interval in seconds. If None, uses default for source.
    """
    # Check if source is in cooldown (from a previous 429)
    cooldown_until = _SOURCE_COOLDOWN_UNTIL.get(source, 0.0)
    now = time.monotonic()
    if now < cooldown_until:
        wait = cooldown_until - now
        logger.info("[%s] in cooldown, waiting %.1fs", source, wait)
        time.sleep(wait)

    interval = min_interval or _SOURCE_INTERVALS.get(source, 2.0)
    last_ts = _SOURCE_LAST_TS.get(source, 0.0)
    elapsed = now - last_ts
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _SOURCE_LAST_TS[source] = time.monotonic()


def set_source_cooldown(source: str, cooldown_sec: float = 60.0) -> None:
    """Put a source into cooldown after receiving HTTP 429.

    Args:
        source: Source name.
        cooldown_sec: How long to wait before retrying (default 60s).
    """
    _SOURCE_COOLDOWN_UNTIL[source] = time.monotonic() + cooldown_sec
    logger.warning("[%s] entering cooldown for %.0fs due to rate limiting", source, cooldown_sec)


# Legacy alias for Semantic Scholar
def rate_limit_semantic_scholar(min_interval_sec: float = 3.0) -> None:
    """Enforce minimum interval between Semantic Scholar requests."""
    rate_limit_source("semantic_scholar", min_interval_sec)


# ---------------------------------------------------------------------------
# Filename / DOI / dict helpers
# ---------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """Remove invalid characters from a filename and truncate to 200 chars.

    Args:
        name: Raw filename string.

    Returns:
        Sanitized filename safe for most file systems.
    """
    name = re.sub(r'[\\/*?:"<>|]+', "_", name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:200]


def doi_normalize(doi: Optional[str]) -> Optional[str]:
    """Normalize a DOI string by stripping URL prefixes.

    Args:
        doi: Raw DOI or DOI URL.

    Returns:
        Normalized DOI (e.g. '10.xxxx/yyy') or None.
    """
    if not doi:
        return None
    doi = doi.strip()
    if doi.startswith("http"):
        m = re.search(r"10\.\d{4,9}/\S+", doi)
        if m:
            return m.group(0)
    return doi


def safe_get(d: dict, *keys, default=None):
    """Safely traverse nested dicts, returning *default* on missing keys.

    Args:
        d: Source dictionary.
        *keys: Sequence of keys to traverse.
        default: Fallback value (default: None).

    Returns:
        Value at the nested path or *default*.
    """
    x = d
    for k in keys:
        if not x:
            return default
        x = x.get(k, None) if isinstance(x, dict) else default
    return x if x is not None else default


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------
def normalize_text(text: str) -> str:
    """Normalize text for robust phrase matching.

    Converts to lowercase, removes hyphens/underscores, collapses whitespace.

    Args:
        text: Input text.

    Returns:
        Normalized text.
    """
    if not text:
        return ""
    t = text.lower()
    t = t.replace("-", "").replace("_", "").replace("/", " ")
    t = re.sub(r'\s+', ' ', t).strip()
    return t


# ---------------------------------------------------------------------------
# Boolean clause parsing
# ---------------------------------------------------------------------------
def parse_clause_units(clause: str) -> Tuple[List[str], List[str], bool]:
    """Parse a boolean clause into positive units, negative units and AND flag.

    Units are phrases/terms used for local relevance matching.

    Args:
        clause: Boolean expression string (may contain AND, OR, NOT, quotes).

    Returns:
        Tuple of (positive_terms, negative_terms, has_and).
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


def match_work_against_clause(work: Dict[str, Any], clause: str, title_only: bool = False) -> bool:
    """Local boolean matching to filter out non-target records from broad API results.

    Args:
        work: Work dict with title/abstract fields.
        clause: Boolean clause to match against.
        title_only: If True, only check the title.

    Returns:
        True if the work matches the clause.
    """
    from .openalex import openalex_abstract_to_text  # lazy to avoid circular

    positives, negatives, has_and = parse_clause_units(clause)
    if not positives:
        return True

    title = (work.get("display_name") or work.get("title") or "")
    abstract = (work.get("abstract_text") or work.get("abstract") or "")
    if not abstract and work.get("abstract_inverted_index"):
        abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))

    text = title if title_only else (title + " " + abstract)
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


def match_work_against_clause_with_reason(
    work: Dict[str, Any],
    clause: str,
    title_only: bool = False,
    match_strictness: float = 1.0,
) -> Tuple[bool, str]:
    """Return (matched, reason) for local boolean filtering.

    Args:
        work: Work dict.
        clause: Boolean clause.
        title_only: If True, only check title.
        match_strictness: 0.0-1.0 fraction of terms that must match.

    Returns:
        Tuple of (matched: bool, reason: str).
    """
    from .openalex import openalex_abstract_to_text

    positives, negatives, has_and = parse_clause_units(clause)
    if not positives:
        return True, "no_positive_units"

    title = (work.get("display_name") or work.get("title") or "")
    abstract = (work.get("abstract_text") or work.get("abstract") or "")
    if not abstract and work.get("abstract_inverted_index"):
        abstract = openalex_abstract_to_text(work.get("abstract_inverted_index"))

    text = title if title_only else (title + " " + abstract)
    normalized_text = normalize_text(text)
    normalized_positives = [normalize_text(p) for p in positives]
    normalized_negatives = [normalize_text(n) for n in negatives]

    hit_negative = [n for n in negatives if normalize_text(n) in normalized_text]
    if hit_negative:
        return False, "hit_negative:" + ",".join(hit_negative[:3])

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


# ---------------------------------------------------------------------------
# Clause splitting
# ---------------------------------------------------------------------------
def split_keywords_into_clauses(keywords: str, max_clauses: int = 200) -> List[str]:
    """Split a boolean keyword string by top-level OR separators.

    Preserves internal AND groups. Top-level separators: OR and commas at
    parentheses depth 0.

    Args:
        keywords: Boolean keyword expression.
        max_clauses: Maximum number of clauses to return.

    Returns:
        List of individual clause strings.
    """
    if not keywords or not keywords.strip():
        return []

    s = keywords.replace("\u201c", '"').replace("\u201d", '"').strip()

    parts = []
    cur = []
    depth = 0
    i = 0
    L = len(s)
    while i < L:
        ch = s[i]
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
        if depth == 0:
            m = re.match(r'\s+OR\s+', s[i:], flags=re.I)
            if m:
                fragment = ''.join(cur).strip()
                if fragment:
                    parts.append(fragment)
                cur = []
                i += m.end()
                continue
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

    def strip_outer_parens(p: str) -> str:
        p = p.strip()
        while p.startswith('(') and p.endswith(')'):
            inner = p[1:-1].strip()
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
        if re.fullmatch(r'^(AND|OR|NOT|\s)+$', p2, flags=re.I):
            continue
        if len(re.sub(r'[^A-Za-z0-9]', '', p2)) < 3:
            continue
        key = p2.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(p2)
    return cleaned[:max_clauses]


# ---------------------------------------------------------------------------
# OpenAlex abstract reconstruction (moved here to avoid circular imports)
# ---------------------------------------------------------------------------
def openalex_abstract_to_text(inv_idx: Any) -> str:
    """Rebuild plain abstract text from OpenAlex abstract_inverted_index.

    Args:
        inv_idx: Inverted index dict mapping tokens to position lists.

    Returns:
        Reconstructed abstract text.
    """
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


# ---------------------------------------------------------------------------
# Source query builder
# ---------------------------------------------------------------------------
def build_source_query(source: str, clause: str, title_only: bool = False) -> str:
    """Build source-specific query text from one clause.

    Args:
        source: Source name (openalex, wos, pubmed, arxiv, crossref, semantic_scholar).
        clause: Generic boolean clause.
        title_only: If True, restrict to title field.

    Returns:
        Source-adapted query string.
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
        # arXiv API does not support quoted phrases with ti:/all: prefix.
        # Split each phrase into words and use AND between them.
        def _arxiv_field_query(phrase: str, prefix: str) -> str:
            words = phrase.strip().split()
            if len(words) == 1:
                return f'{prefix}:"{words[0]}"'
            return " AND ".join([f'{prefix}:"{w}"' for w in words])

        prefix = "ti" if title_only else "all"
        parts = [_arxiv_field_query(p, prefix) for p in positives]
        if has_and:
            return " AND ".join(parts)
        return " OR ".join(parts)

    if source == "crossref":
        if has_and:
            return " AND ".join([f'"{p}"' for p in positives])
        else:
            return " ".join([f'"{p}"' for p in positives])

    if source == "semantic_scholar":
        return " ".join(positives)

    if source == "openalex":
        return " ".join(positives)

    return clause.strip()


# ---------------------------------------------------------------------------
# Source stats tracking
# ---------------------------------------------------------------------------
_SOURCE_STATS: Dict[str, Dict[str, int]] = {}


def set_source_stats(source: str, scanned_raw: int, returned: int) -> None:
    """Record per-source runtime stats for debug logging.

    Args:
        source: Source name.
        scanned_raw: Number of raw results scanned.
        returned: Number of results returned after filtering.
    """
    _SOURCE_STATS[source] = {
        "scanned_raw": max(0, int(scanned_raw)),
        "returned": max(0, int(returned)),
    }


def get_source_stats(source: str) -> Dict[str, int]:
    """Retrieve stats for a source.

    Args:
        source: Source name.

    Returns:
        Dict with 'scanned_raw' and 'returned' keys, or empty dict.
    """
    return _SOURCE_STATS.get(source, {})
