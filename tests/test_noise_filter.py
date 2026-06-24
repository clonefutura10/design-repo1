"""Unit tests for the noise / EDC-scaffolding filter."""

from __future__ import annotations

import pytest

from src.pdf_parser.field_identifier import CRFField
from src.resolution.noise_filter import is_noise_field, _is_edc_scaffolding


def _field(label: str) -> CRFField:
    return CRFField(field_label=label, form_code="CM", page_index=0)


# ─── EDC scaffolding must be filtered ─────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "30 MEDPREF7",          # numbered EDC var def
    "32 MEDGROUP $200",     # var def with SAS length
    "42 DRGDICTV",          # numbered raw var
    "Z_SPCBEDB",            # SAS var name (underscore)
    "CMSPID",               # bare upper-case EDC var
    "DRGDICTV",
    "MEDGEN1",
    "1 = Yes",              # codelist value
    "C49671 = kg/m2",       # NCI-coded value
    "6 = Optional assent to donate",
])
def test_edc_scaffolding_is_detected(label):
    assert _is_edc_scaffolding(label) is True
    assert is_noise_field(_field(label)) is True


# ─── Real CRF labels must NOT be filtered ─────────────────────────────────────

@pytest.mark.parametrize("label", [
    "Weight", "Date", "Comment", "Sex", "Ethnicity", "Race",
    "BMI", "ECG", "FVC",                       # short acronyms — must survive
    "Other race, specify",
    "Hispanic or Latino",
    "Date subject signed main informed consent",
    "Is the subject participating in optional DNA sampling?",
])
def test_real_labels_not_edc(label):
    assert _is_edc_scaffolding(label) is False


@pytest.mark.parametrize("label", [
    "Weight", "Vital signs collection date",
    "Is the subject participating in Flow cytometry sampling?",
])
def test_real_labels_pass_filter(label):
    assert is_noise_field(_field(label)) is False


# ─── Classic noise categories still filtered ──────────────────────────────────

@pytest.mark.parametrize("label", [
    "1 of 948",                 # page number
    "(24582)",                  # internal number
    "Generated On: 2020",       # header leak
    "ab",                       # too short
])
def test_classic_noise_filtered(label):
    assert is_noise_field(_field(label)) is True
