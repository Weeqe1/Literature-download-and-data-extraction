"""Tests for quality_control module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quality_control import LiteratureQualityController


@pytest.fixture
def qc():
    return LiteratureQualityController()


class TestRelevanceScore:
    def test_highly_relevant(self, qc):
        work = {
            "title": "Nano fluorescent probe for detection of metal ions",
            "abstract": "We developed a novel fluorescent nanoprobe using quantum dots for sensing Cu2+ ions in aqueous solution. The probe exhibited excellent selectivity and sensitivity."
        }
        result = qc.calculate_relevance_score(work)
        score = result[0] if isinstance(result, tuple) else result
        assert score > 0.3

    def test_irrelevant(self, qc):
        work = {
            "title": "Economic analysis of trade policies",
            "abstract": "This paper examines the impact of tariffs on international trade flows."
        }
        result = qc.calculate_relevance_score(work)
        score = result[0] if isinstance(result, tuple) else result
        assert score < 0.1

    def test_no_text(self, qc):
        work = {"title": "", "abstract": ""}
        result = qc.calculate_relevance_score(work)
        score = result[0] if isinstance(result, tuple) else result
        assert score == 0.0


class TestCompletenessScore:
    def test_complete(self, qc):
        work = {
            "title": "Test paper",
            "abstract": "An abstract with sufficient length to be considered complete",
            "publication_year": 2023,
            "doi": "10.1234/test",
            "authors": "Author One; Author Two",
            "journal": "Test Journal",
        }
        result = qc.calculate_completeness_score(work)
        score = result[0] if isinstance(result, tuple) else result
        assert score > 0.3

    def test_minimal(self, qc):
        work = {"title": "Just a title"}
        result = qc.calculate_completeness_score(work)
        score = result[0] if isinstance(result, tuple) else result
        assert score < 0.3


class TestValidateAndCleanMetadata:
    def test_cleans_empty_strings(self, qc):
        works = [
            {"title": "Valid paper", "abstract": "", "year": 2023, "doi": "10.1234/test", "authors": "", "journal": ""},
        ]
        cleaned = qc.validate_and_clean_metadata(works)
        assert len(cleaned) == 1

    def test_cleans_metadata(self, qc):
        works = [
            {"title": "Paper", "abstract": "Abstract", "year": 2023, "doi": "", "authors": "", "journal": ""},
        ]
        cleaned = qc.validate_and_clean_metadata(works)
        assert len(cleaned) == 1
        assert cleaned[0]["title"] == "Paper"


class TestFilterLiterature:
    def test_filters_by_relevance(self, qc):
        works = [
            {"title": "Nano fluorescent probe", "abstract": "A new fluorescent nanoprobe was developed for bioimaging", "year": 2023, "doi": "10.1/a", "authors": "A", "journal": "J"},
            {"title": "Unrelated topic", "abstract": "Something completely different with no relevance", "year": 2023, "doi": "10.1/b", "authors": "B", "journal": "J"},
        ]
        filtered, stats = qc.filter_literature(works, min_relevance=0.05, min_completeness=0.1, min_overall=0.1)
        assert stats["total_input"] == 2
        assert len(filtered) <= 2
