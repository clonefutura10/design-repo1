"""Tests for output provenance / reproducibility stamping and error surfacing."""

from __future__ import annotations

import fitz

from config.version import provenance, TOOL_VERSION, MSG_VERSION


def test_provenance_record_complete():
    p = provenance()
    assert p["tool_version"] == TOOL_VERSION
    assert p["msg_version"] == MSG_VERSION
    assert p["generated_utc"].endswith("Z")
    # Rule-set fingerprints present (so an output can be tied to its rules).
    assert p["form_rules_fp"]
    assert p["universal_rules_fp"]


def test_pdf_metadata_stamped(blank_job):
    doc = fitz.open(str(blank_job.output_pdf_path))
    try:
        md = doc.metadata
        assert TOOL_VERSION in (md.get("creator") or "")
        assert "tool_version=" in (md.get("keywords") or "")
    finally:
        doc.close()


def test_no_silent_write_failures(blank_job):
    # Every annotation either rendered or was explicitly accounted for.
    assert blank_job.stats.get("write_failures", 0) == 0


def test_review_counts_present(blank_job):
    assert "review_required_count" in blank_job.stats
    assert blank_job.stats["review_required_count"] >= 0
