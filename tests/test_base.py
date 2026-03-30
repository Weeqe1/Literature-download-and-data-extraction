"""Tests for etl_ensemble.sources.base utilities."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl_ensemble.sources.base import (
    sanitize_filename,
    doi_normalize,
    safe_get,
    normalize_text,
    parse_clause_units,
    split_keywords_into_clauses,
    match_work_against_clause,
    match_work_against_clause_with_reason,
    build_source_query,
)


# --- sanitize_filename ---

class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("hello world.pdf") == "hello world.pdf"

    def test_special_chars_replaced(self):
        result = sanitize_filename('file<>:"/\\|?*.pdf')
        for ch in '<>:"/\\|?*':
            assert ch not in result

    def test_whitespace_collapsed(self):
        assert "  " not in sanitize_filename("a    b")

    def test_truncation(self):
        long = "x" * 300
        assert len(sanitize_filename(long)) <= 200

    def test_empty(self):
        assert sanitize_filename("") == ""


# --- doi_normalize ---

class TestDoiNormalize:
    def test_plain_doi(self):
        assert doi_normalize("10.1234/abcd") == "10.1234/abcd"

    def test_url_doi(self):
        assert doi_normalize("https://doi.org/10.1234/abcd") == "10.1234/abcd"

    def test_http_doi(self):
        assert doi_normalize("http://dx.doi.org/10.5678/test") == "10.5678/test"

    def test_none(self):
        assert doi_normalize(None) is None

    def test_empty(self):
        assert doi_normalize("") is None

    def test_whitespace(self):
        assert doi_normalize("  10.1234/xyz  ") == "10.1234/xyz"


# --- safe_get ---

class TestSafeGet:
    def test_nested(self):
        d = {"a": {"b": {"c": 42}}}
        assert safe_get(d, "a", "b", "c") == 42

    def test_missing_key(self):
        assert safe_get({"a": 1}, "b") is None

    def test_default(self):
        assert safe_get({}, "x", default=99) == 99

    def test_non_dict_intermediate(self):
        assert safe_get({"a": "string"}, "a", "b", default="fallback") == "fallback"


# --- normalize_text ---

class TestNormalizeText:
    def test_lowercase(self):
        assert normalize_text("HELLO") == "hello"

    def test_hyphens_removed(self):
        assert normalize_text("nano-probe") == "nanoprobe"

    def test_underscores_removed(self):
        assert normalize_text("quantum_dot") == "quantumdot"

    def test_slashes_to_space(self):
        assert normalize_text("a/b") == "a b"

    def test_whitespace_collapsed(self):
        assert normalize_text("a   b") == "a b"

    def test_empty(self):
        assert normalize_text("") == ""

    def test_none(self):
        assert normalize_text(None) == ""


# --- parse_clause_units ---

class TestParseClauseUnits:
    def test_simple_quoted(self):
        pos, neg, has_and = parse_clause_units('"nano probe" OR "quantum dot"')
        assert "nano probe" in pos
        assert "quantum dot" in pos
        assert not has_and

    def test_and_clause(self):
        pos, neg, has_and = parse_clause_units('"A" AND "B"')
        assert has_and
        assert len(pos) == 2

    def test_not_clause(self):
        pos, neg, has_and = parse_clause_units('"probe" NOT "toxic"')
        assert "toxic" in neg or "toxic" in [n.lower() for n in neg]
        assert any("probe" in p for p in pos)

    def test_empty(self):
        pos, neg, has_and = parse_clause_units("")
        assert pos == []
        assert neg == []
        assert not has_and


# --- split_keywords_into_clauses ---

class TestSplitKeywordsIntoClauses:
    def test_or_split(self):
        keywords = '"nano probe" OR "quantum dot" OR "fluorescent sensor"'
        clauses = split_keywords_into_clauses(keywords)
        assert len(clauses) >= 2

    def test_preserves_and(self):
        keywords = '("A" AND "B") OR ("C")'
        clauses = split_keywords_into_clauses(keywords)
        # One clause should contain AND
        assert any("and" in c.lower() for c in clauses)

    def test_empty(self):
        assert split_keywords_into_clauses("") == []

    def test_deduplication(self):
        keywords = '"nano probe" OR "nano probe"'
        clauses = split_keywords_into_clauses(keywords)
        assert len(clauses) == 1


# --- match_work_against_clause ---

class TestMatchWorkAgainstClause:
    def test_match_positive(self):
        work = {"display_name": "Nano fluorescent probe for detection", "abstract_text": "A new probe was developed"}
        assert match_work_against_clause(work, '"nano fluorescent probe"')

    def test_no_match(self):
        work = {"display_name": "Completely unrelated paper", "abstract_text": "Nothing here"}
        assert not match_work_against_clause(work, '"quantum dot"')

    def test_negative_match(self):
        work = {"display_name": "Toxic nano probe", "abstract_text": "Very toxic material"}
        assert not match_work_against_clause(work, '"nano probe" NOT "toxic"')


# --- match_work_against_clause_with_reason ---

class TestMatchWithReason:
    def test_matched(self):
        work = {"display_name": "Nano fluorescent probe", "abstract_text": ""}
        ok, reason = match_work_against_clause_with_reason(work, '"nano fluorescent probe"')
        assert ok
        assert "matched" in reason

    def test_not_matched(self):
        work = {"display_name": "Unrelated", "abstract_text": ""}
        ok, reason = match_work_against_clause_with_reason(work, '"quantum dot probe"')
        assert not ok

    def test_strictness(self):
        work = {"display_name": "Nano probe fluorescent sensor", "abstract_text": ""}
        # With strictness 0.5, matching 2 out of 3 terms should pass
        ok, reason = match_work_against_clause_with_reason(
            work, '"nano" AND "probe" AND "missing_term"', match_strictness=0.5
        )
        assert ok


# --- build_source_query ---

class TestBuildSourceQuery:
    def test_pubmed_query(self):
        q = build_source_query("pubmed", '"nano probe"')
        assert "[Title/Abstract]" in q or "nano" in q

    def test_arxiv_query(self):
        q = build_source_query("arxiv", '"nano probe"')
        assert "all:" in q or "ti:" in q

    def test_wos_query(self):
        q = build_source_query("wos", '"nano probe" OR "quantum dot"')
        assert '"' in q
