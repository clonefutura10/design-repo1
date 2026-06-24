"""
Mapping-specification export.

Produces the field-to-SDTM mapping table that accompanies an annotated CRF —
the traceability artifact SDTM reviewers actually work from (and the place a
human verifies the tool's output without paging through the whole aCRF).

One row per unique (form, field) mapping, with the resolved SDTM target, the
where/when qualifier, the supplemental/NOT-SUBMITTED flags, and — crucially for
review triage — the confidence and resolution tier of each mapping.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from src.pdf_parser.field_identifier import CRFField
from src.resolution.models import ResolutionResult


_COLUMNS = [
    "form_code", "form_name", "visit", "page",
    "field_label",
    "sdtm_domain", "sdtm_variable", "where_clause", "codelist_code",
    "is_supplemental", "is_not_submitted",
    "annotation", "additional_annotations",
    "confidence", "tier", "review_flag",
]


def _annotation_string(r: ResolutionResult) -> str:
    """Human-readable primary annotation (mirrors what is drawn on the PDF)."""
    if r.is_not_submitted:
        return "[NOT SUBMITTED]"
    if not r.sdtm_domain or not r.sdtm_variable:
        return ""
    return r.annotation_text


def _review_flag(r: ResolutionResult) -> str:
    """Triage hint for a human reviewer."""
    if not r.resolved and not r.is_not_submitted:
        return "UNRESOLVED"
    if r.is_not_submitted:
        return ""
    if r.confidence and r.confidence < 0.90:
        return "LOW_CONFIDENCE"
    return ""


def build_mapping_rows(
    results: Iterable[ResolutionResult],
    fields: Iterable[CRFField],
) -> list[dict]:
    """Build mapping-spec rows from aligned results and fields."""
    rows: list[dict] = []
    for fld, r in zip(fields, results):
        add = []
        for m in getattr(r, "additional_mappings", None) or []:
            dom = m.get("sdtm_domain") or m.get("domain", "")
            var = m.get("sdtm_variable") or m.get("variable", "")
            if dom and var:
                add.append(f"{dom}.{var}")
        rows.append({
            "form_code": fld.form_code or "",
            "form_name": getattr(fld, "form_name", "") or "",
            "visit": getattr(fld, "folder", "") or "",
            "page": (fld.page_index + 1) if fld.page_index is not None else "",
            "field_label": fld.field_label or "",
            "sdtm_domain": r.sdtm_domain or "",
            "sdtm_variable": r.sdtm_variable or "",
            "where_clause": getattr(r, "where_clause", "") or "",
            "codelist_code": r.codelist_code or "",
            "is_supplemental": r.is_supplemental,
            "is_not_submitted": r.is_not_submitted,
            "annotation": _annotation_string(r),
            "additional_annotations": " / ".join(add),
            "confidence": round(r.confidence, 3) if r.confidence else 0.0,
            "tier": r.tier.value if hasattr(r.tier, "value") else str(r.tier),
            "review_flag": _review_flag(r),
        })
    return rows


def write_mapping_csv(
    results: Iterable[ResolutionResult],
    fields: Iterable[CRFField],
    output_path: Path,
) -> int:
    """Write the mapping spec to CSV. Returns the number of rows written."""
    rows = build_mapping_rows(results, fields)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
