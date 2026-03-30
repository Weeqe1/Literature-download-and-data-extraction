"""Tests for build_clean_dataset utilities."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from build_clean_dataset import (
    flatten_dict,
    extract_numeric_range,
    extract_lod_value,
    clean_numeric_field,
)


class TestFlattenDict:
    def test_simple(self):
        d = {"a": 1, "b": 2}
        assert flatten_dict(d) == {"a": 1, "b": 2}

    def test_nested(self):
        d = {"a": {"b": {"c": 3}}}
        result = flatten_dict(d)
        assert "a__b__c" in result

    def test_value_extraction(self):
        d = {"field": {"value": 42, "confidence": 0.9}}
        result = flatten_dict(d)
        assert result["field"] == 42

    def test_non_dict(self):
        assert flatten_dict("not a dict") == {}

    def test_empty(self):
        assert flatten_dict({}) == {}


class TestExtractNumericRange:
    def test_range_to(self):
        low, high, unit = extract_numeric_range("0.02 to 50.00 ng/mL")
        assert low == 0.02
        assert high == 50.0
        assert unit == "ng/mL"

    def test_range_dash(self):
        low, high, unit = extract_numeric_range("1.5-2.0 nm")
        assert low == 1.5
        assert high == 2.0

    def test_single_number(self):
        low, high, unit = extract_numeric_range("42.5 nM")
        assert low == 42.5
        assert high == 42.5

    def test_non_string(self):
        low, high, unit = extract_numeric_range(None)
        assert low is None

    def test_no_number(self):
        low, high, unit = extract_numeric_range("not a number")
        assert low is None


class TestExtractLodValue:
    def test_simple(self):
        val, unit = extract_lod_value("0.003 ng/mL")
        assert val == 0.003
        assert unit == "ng/mL"

    def test_with_less_than(self):
        val, unit = extract_lod_value("< 0.057 μg/mL")
        assert val == 0.057

    def test_scientific_notation(self):
        val, unit = extract_lod_value("1.2e-5 mol/L")
        assert val == pytest.approx(1.2e-5)

    def test_non_string(self):
        val, unit = extract_lod_value(None)
        assert val is None


class TestCleanNumericField:
    def test_float(self):
        assert clean_numeric_field(3.14) == 3.14

    def test_int(self):
        assert clean_numeric_field(42) == 42.0

    def test_string_number(self):
        assert clean_numeric_field("42.5") == 42.5

    def test_with_less_than(self):
        assert clean_numeric_field("< 0.05") == 0.05

    def test_with_unit(self):
        assert clean_numeric_field("10.5 nm") == 10.5

    def test_none(self):
        assert clean_numeric_field(None) is None

    def test_empty_string(self):
        assert clean_numeric_field("") is None

    def test_null_string(self):
        assert clean_numeric_field("null") is None

    def test_not_a_number(self):
        assert clean_numeric_field("not specified") is None
