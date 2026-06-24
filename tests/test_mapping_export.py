"""Unit tests for the mapping-spec CSV export."""

from __future__ import annotations

import csv

from src.pdf_parser.field_identifier import CRFField
from src.resolution.models import ResolutionResult, ResolutionTier
from src.annotator.mapping_export import build_mapping_rows, write_mapping_csv, _COLUMNS


def _field(label, form="VS", page=4, visit="Visit 1", name="Vital Signs"):
    return CRFField(field_label=label, form_code=form, form_name=name,
                    folder=visit, page_index=page)


def _res(**kw):
    kw.setdefault("resolved", True)
    kw.setdefault("tier", ResolutionTier.TIER0_EXACT)
    return ResolutionResult(**kw)


def test_rows_capture_core_mapping():
    fields = [_field("Temperature")]
    results = [_res(sdtm_domain="VS", sdtm_variable="VSORRES",
                    where_clause="VSTESTCD = TEMP", confidence=0.96)]
    rows = build_mapping_rows(results, fields)
    r = rows[0]
    assert r["sdtm_domain"] == "VS"
    assert r["sdtm_variable"] == "VSORRES"
    assert r["where_clause"] == "VSTESTCD = TEMP"
    assert r["page"] == 5            # page_index 4 -> 1-based 5
    assert r["visit"] == "Visit 1"
    assert r["review_flag"] == ""    # high confidence


def test_low_confidence_flagged():
    rows = build_mapping_rows(
        [_res(sdtm_domain="VS", sdtm_variable="VSORRES", confidence=0.85)],
        [_field("x")],
    )
    assert rows[0]["review_flag"] == "LOW_CONFIDENCE"


def test_unresolved_flagged():
    rows = build_mapping_rows(
        [ResolutionResult(resolved=False, tier=ResolutionTier.UNRESOLVED)],
        [_field("mystery field")],
    )
    assert rows[0]["review_flag"] == "UNRESOLVED"


def test_not_submitted_annotation():
    rows = build_mapping_rows(
        [_res(is_not_submitted=True, confidence=1.0)],
        [_field("prompt question")],
    )
    assert rows[0]["annotation"] == "[NOT SUBMITTED]"
    assert rows[0]["review_flag"] == ""


def test_csv_written_with_header(tmp_path):
    out = tmp_path / "m.csv"
    n = write_mapping_csv(
        [_res(sdtm_domain="DM", sdtm_variable="SEX", confidence=0.96)],
        [_field("Sex", form="DM")],
        out,
    )
    assert n == 1
    with out.open() as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == _COLUMNS
        row = next(reader)
        assert row["sdtm_variable"] == "SEX"
