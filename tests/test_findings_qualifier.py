"""Unit tests for Findings TESTCD qualification and MSG where-clause style."""

from __future__ import annotations

from src.resolution.models import ResolutionResult
from src.resolution.findings_qualifier import (
    FindingsQualifierResolver,
    test_name_for_code as _name_for_code,
    _fmt_where,
)


def _vs(variable: str = "VSORRES") -> ResolutionResult:
    return ResolutionResult(sdtm_domain="VS", sdtm_variable=variable)


def test_where_clause_is_unquoted_by_default():
    # MSG v2.0 pt.14: explicit values are not quoted.
    assert _fmt_where("VSTESTCD", "WEIGHT") == "VSTESTCD = WEIGHT"
    assert '"' not in _fmt_where("VSTESTCD", "TEMP")


def test_direct_label_resolves_testcd():
    r = FindingsQualifierResolver()
    wc = r.resolve_qualifier(_vs(), field_label="Temperature")
    assert wc == "VSTESTCD = TEMP"


def test_context_label_resolves_testcd():
    r = FindingsQualifierResolver()
    wc = r.resolve_qualifier(
        _vs(), field_label="Result",
        context_labels_before=["Weight"],
    )
    assert wc == "VSTESTCD = WEIGHT"


def test_ambiguous_grid_returns_none():
    r = FindingsQualifierResolver()
    wc = r.resolve_qualifier(
        _vs(), field_label="Result",
        value_options=["Systolic blood pressure", "Temperature", "Weight"],
    )
    assert wc is None


def test_placeholder_testcode_not_emitted():
    r = FindingsQualifierResolver()
    # "Vital signs" maps to the synthetic VSALL placeholder, never a clause.
    wc = r.resolve_qualifier(_vs(), field_label="Vital signs")
    assert wc is None


def test_non_findings_domain_skipped():
    r = FindingsQualifierResolver()
    res = ResolutionResult(sdtm_domain="DM", sdtm_variable="AGE")
    assert r.resolve_qualifier(res, field_label="Age") is None


def test_test_name_lookup():
    assert _name_for_code("VS", "WEIGHT") is not None
    assert _name_for_code("VS", "WEIGHT").istitle()
    assert _name_for_code("VS", "NONSENSE") is None
