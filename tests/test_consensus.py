"""Tests for etl_ensemble.consensus_engine."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from etl_ensemble.consensus_engine import (
    is_number,
    numeric_close,
    get_field_tolerance,
    compare_field_values,
    compare_outputs,
)


class TestIsNumber:
    def test_int(self):
        assert is_number(42)

    def test_float(self):
        assert is_number(3.14)

    def test_string_number(self):
        assert is_number("42.5")

    def test_none(self):
        assert not is_number(None)

    def test_text(self):
        assert not is_number("hello")

    def test_empty_string(self):
        assert not is_number("")


class TestNumericClose:
    def test_exact_match(self):
        assert numeric_close(10.0, 10.0)

    def test_within_tolerance(self):
        assert numeric_close(10.0, 10.05, rel_tol=0.01)

    def test_outside_tolerance(self):
        assert not numeric_close(10.0, 15.0, rel_tol=0.01, abs_tol=1.0)

    def test_abs_tolerance(self):
        assert numeric_close(100.0, 102.0, abs_tol=5.0)

    def test_non_numeric(self):
        assert not numeric_close("abc", 10)


class TestGetFieldTolerance:
    def test_known_field(self):
        rel, abs_tol = get_field_tolerance("emission_wavelength_nm")
        assert rel == 0.01
        assert abs_tol == 5.0

    def test_unknown_field(self):
        rel, abs_tol = get_field_tolerance("unknown_field", default_rel=0.05, default_abs=2.0)
        assert rel == 0.05
        assert abs_tol == 2.0


class TestCompareFieldValues:
    def test_numeric_agreement(self):
        vals = [
            {"model_id": "m1", "field": "size_nm", "value": 10.0, "resp": {}},
            {"model_id": "m2", "field": "size_nm", "value": 10.1, "resp": {}},
        ]
        ok, value, details = compare_field_values(vals, field_name="size_nm")
        assert ok
        assert value is not None

    def test_string_agreement(self):
        vals = [
            {"model_id": "m1", "field": "material", "value": "CdSe", "resp": {}},
            {"model_id": "m2", "field": "material", "value": "CdSe", "resp": {}},
        ]
        ok, value, details = compare_field_values(vals)
        assert ok
        assert value == "CdSe"

    def test_disagreement(self):
        vals = [
            {"model_id": "m1", "field": "size_nm", "value": 10.0, "resp": {}},
            {"model_id": "m2", "field": "size_nm", "value": 50.0, "resp": {}},
        ]
        ok, value, details = compare_field_values(vals, field_name="size_nm")
        assert not ok

    def test_empty(self):
        ok, value, details = compare_field_values([])
        assert not ok


class TestCompareOutputs:
    def test_agreed_fields(self):
        model_results = [
            {"model_id": "m1", "resp": {"size_nm": {"value": 10.0}, "material": {"value": "CdSe"}}},
            {"model_id": "m2", "resp": {"size_nm": {"value": 10.1}, "material": {"value": "CdSe"}}},
        ]
        result = compare_outputs(model_results)
        assert "size_nm" in result["agreed"]
        assert "material" in result["agreed"]

    def test_disagreed_fields(self):
        model_results = [
            {"model_id": "m1", "resp": {"size_nm": {"value": 10.0}}},
            {"model_id": "m2", "resp": {"size_nm": {"value": 999.0}}},
        ]
        result = compare_outputs(model_results)
        assert "size_nm" in result["disagreed"]
