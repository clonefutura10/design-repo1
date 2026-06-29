"""Tests for derived-variable marking and MedDRA/dictionary re-annotation."""

from __future__ import annotations

from src.resolution.tier0_rules import (
    Tier0Rules, set_study_context, _is_derived_variable,
)


def _resolver():
    set_study_context({"DM", "AE", "CM", "MH"})
    return Tier0Rules()


# ─── Derived-variable detection (MSG dashed-border eligibility) ────────────────

def test_assigned_vars_are_derived():
    for v in ("AGE", "AGEU", "BMI", "EPOCH"):
        assert _is_derived_variable(v) is True


def test_coded_vars_are_derived():
    for v in ("AEDECOD", "AEBODSYS", "AESOC", "CMCLAS", "AELLT", "AESTDY"):
        assert _is_derived_variable(v) is True


def test_collected_vars_not_derived():
    for v in ("AETERM", "VSORRES", "CMTRT", "DMSEX", "BRTHDTC"):
        assert _is_derived_variable(v) is False


# ─── AGE / AGEU resolve and are flagged derived ───────────────────────────────

def test_age_marked_derived():
    r = _resolver().resolve(form_code="DM", field_label="Age")
    assert r is not None and r.sdtm_variable == "AGE"
    assert r.is_derived is True


# ─── MedDRA / dictionary fields annotated (not dropped) as derived ────────────

def test_meddra_pt_name_to_decod():
    r = _resolver().resolve(form_code="AE", field_label="MedDRA Preferred Term Name")
    assert r is not None and r.sdtm_variable == "AEDECOD"
    assert r.is_derived is True


def test_meddra_soc_to_bodsys():
    r = _resolver().resolve(form_code="AE", field_label="MedDRA System Organ Class Name")
    assert r is not None and r.sdtm_variable == "AEBODSYS"
    assert r.is_derived is True


def test_med_dictionary_text_to_decod():
    r = _resolver().resolve(form_code="CM", field_label="Medication dictionary text")
    assert r is not None and r.sdtm_variable == "CMDECOD"
    assert r.is_derived is True


def test_dictionary_version_maps_to_supp_qualifier():
    # Dictionary version is submitted as a SUPP-- qualifier (Origin = Assigned),
    # not "[NOT SUBMITTED]".
    r = _resolver().resolve(form_code="AE", field_label="MedDRA version")
    assert r is not None
    assert r.is_not_submitted is False
    assert r.sdtm_variable == "MEDDRAV"
    assert r.is_supplemental is True
    assert r.is_derived is True


def test_meddra_standard_wordings_to_coded_variables():
    # Older CRFs display dictionary-coding columns with the standard CDISC
    # wordings (no "meddra" prefix); these map to the derived coded variables.
    res = _resolver()
    assert res.resolve(form_code="AE", field_label="Dictionary-Derived Term").sdtm_variable == "AEDECOD"
    assert res.resolve(form_code="AE", field_label="Lowest Level Term").sdtm_variable == "AELLT"
    assert res.resolve(form_code="MH", field_label="Body System or Organ Class").sdtm_variable == "MHBODSYS"
