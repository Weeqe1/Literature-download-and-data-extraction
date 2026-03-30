"""Source-specific search modules for literature harvester."""
from .base import (
    sanitize_filename,
    doi_normalize,
    safe_get,
    normalize_text,
    parse_clause_units,
    match_work_against_clause,
    match_work_against_clause_with_reason,
    split_keywords_into_clauses,
    rate_limit,
    openalex_abstract_to_text,
)
