"""Unit tests locking in the SDTM-MSG v2.0 annotation format decisions."""

from __future__ import annotations

from src.resolution.models import ResolutionResult
from src.annotator import pdf_writer as w


# ─── Colour sequence (MSG v2.0 §3.1.2 pt.7) ───────────────────────────────────

def test_msg_colour_sequence_exact():
    seq = [tuple(round(c * 255) for c in col) for col in w._MSG_COLOUR_SEQUENCE]
    assert seq == [
        (191, 255, 255),  # blue
        (255, 255, 150),  # yellow
        (150, 255, 150),  # green
        (255, 190, 155),  # orange
    ]


def test_page_colour_map_is_positional():
    cmap = w._build_page_colour_map(["VS", "DM", "LB"])
    assert cmap["VS"] == w._seq_colour(0)
    assert cmap["DM"] == w._seq_colour(1)
    assert cmap["LB"] == w._seq_colour(2)


def test_darken_produces_darker_shade():
    d = w._darken((0.749, 1.0, 1.0))
    assert all(d[i] < (0.749, 1.0, 1.0)[i] for i in range(3))


# ─── Header label format (MSG v2.0 pt.5: "DM (Demographics)") ─────────────────

def test_domain_header_title_case_with_acronym():
    assert w._get_domain_full_name("VS") == "Vital Signs"
    assert w._get_domain_full_name("EG") == "ECG Test Results"      # acronym kept
    assert w._get_domain_full_name("FA") == "Findings About Events or Interventions"


# ─── Variable annotation text (standalone names, when keyword, SUPP "in") ──────

def test_standalone_variable_no_domain_prefix():
    res = ResolutionResult(sdtm_domain="VS", sdtm_variable="VSORRES", resolved=True)
    anns = w._build_annotations_list(res)
    assert anns[0]["text"] == "VSORRES"          # not "VS.VSORRES"


def test_supp_in_format():
    res = ResolutionResult(
        sdtm_domain="DM", sdtm_variable="RACEOTH",
        resolved=True, is_supplemental=True,
    )
    anns = w._build_annotations_list(res)
    assert anns[0]["text"] == "RACEOTH in SUPPDM"
    assert anns[0]["where_clause"] == ""


def test_findings_where_clause_carried():
    res = ResolutionResult(
        sdtm_domain="VS", sdtm_variable="VSORRES",
        resolved=True, where_clause="VSTESTCD = TEMP",
    )
    anns = w._build_annotations_list(res)
    assert anns[0]["where_clause"] == "VSTESTCD = TEMP"


def test_not_submitted_entry():
    res = ResolutionResult(resolved=True, is_not_submitted=True)
    anns = w._build_annotations_list(res)
    assert anns[0]["is_not_submitted"] is True
    assert anns[0]["text"] == "[NOT SUBMITTED]"


# ─── TOC structure matches the reference hierarchy ────────────────────────────

def test_toc_reference_structure():
    toc = w._build_toc(
        form_first_page={"VS1": (4, "VS1")},
        form_domains={"VS1": "VS"},
        form_visits={"VS1": [("Visit 1", 4)]},
        form_names={"VS1": "Vital Signs"},
        study_id="D1234C00001",
    )
    flat = [(lvl, title) for lvl, title, _ in toc]
    # Study root present.
    assert flat[0] == (1, "D1234C00001")
    assert (2, "By Domain") in flat
    assert (2, "By Visit") in flat
    # Domain label and "Domain: Form Name (CODE)" form label.
    assert any(t == "VS: Vital Signs" for _, t in flat)
    assert any(t == "VS: Vital Signs (VS1)" for _, t in flat)
