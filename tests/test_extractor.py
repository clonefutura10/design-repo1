"""Unit tests for PDF extraction routing and EDC spec-table detection."""

from __future__ import annotations

from src.pdf_parser.field_identifier import page_has_field_numbers
from src.pdf_parser.extractor import _is_spec_table_page


# ─── Parser routing (numbered vs position-based) ──────────────────────────────

def test_numbered_layout_detected():
    lines = ["Weight", "2", "Height", "3"]
    assert page_has_field_numbers(lines) is True


def test_numberless_layout_detected():
    lines = ["Sex", "Male", "Female", "Ethnicity"]
    assert page_has_field_numbers(lines) is False


# ─── EDC spec-table page detection ────────────────────────────────────────────

def test_spec_table_page_detected():
    text = (
        "Form: Prior Biologics for Asthma (CM1)\n"
        "Field Name  Data Type  Field Label  SAS Format  SAS Label  Values\n"
        "CMSPID  3  Medication number  8  Medication Number\n"
    )
    assert _is_spec_table_page(text) is True


def test_real_screen_not_spec_table():
    text = (
        "Form: Vital Signs (VS1)\n"
        "Result\nVSORRES\nUnit\n"
    )
    assert _is_spec_table_page(text) is False


def test_partial_columns_not_spec_table():
    # "Field Name" alone (e.g. appearing in prose) must not trip the detector.
    text = "Form: X\nPlease enter the Field Name of the device\n"
    assert _is_spec_table_page(text) is False
