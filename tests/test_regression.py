"""End-to-end golden regression tests on the real CRFs.

These lock in the behaviour built up over the project. Thresholds are ranges so
incidental changes don't break the suite, but real regressions (rate collapse,
EDC pages annotated again, boxes no longer editable, colours gone) do.
"""

from __future__ import annotations

import fitz


def _freetext_annots(page):
    return [a for a in (page.annots() or []) if a.type[1] == "FreeText"]


# ─── Resolution rate is healthy on every layout family ────────────────────────

def test_blank_crf_resolution_rate(blank_job):
    assert blank_job.stats["resolution_rate"] >= 88.0


def test_numberless_crf_resolution_rate(numberless_job):
    assert numberless_job.stats["resolution_rate"] >= 80.0


def test_db_crf_matches_blank(db_job, blank_job):
    # The DB/Raw CRF (spec tables excluded) should resolve like the blank.
    assert db_job.stats["resolution_rate"] >= 88.0
    assert db_job.stats["fields_after_noise_filter"] == \
        blank_job.stats["fields_after_noise_filter"]


# ─── Annotations are real, editable FreeText with baked colour fill ───────────

def test_annotations_are_editable_freetext(blank_doc):
    total = sum(len(_freetext_annots(blank_doc[pi])) for pi in range(blank_doc.page_count))
    assert total > 500


def test_msg_fill_colours_present(blank_doc):
    msg = {(0.75, 1.0, 1.0), (1.0, 1.0, 0.59), (0.59, 1.0, 0.59), (1.0, 0.75, 0.61)}
    found = set()
    for pi in range(min(blank_doc.page_count, 120)):
        for o in blank_doc[pi].get_drawings():
            f = o.get("fill")
            if f:
                found.add(tuple(round(x, 2) for x in f))
    assert msg & found, "no MSG sequence fill colours found in output"


def test_no_box_runs_off_page(blank_doc):
    off = 0
    for pi in range(blank_doc.page_count):
        pw = blank_doc[pi].rect.width
        for o in blank_doc[pi].get_drawings():
            if not o.get("fill"):
                continue
            for it in o["items"]:
                if it[0] == "re" and it[1].x1 > pw - 1.0:
                    off += 1
    assert off == 0


# ─── Bookmarks match the reference hierarchy ──────────────────────────────────

def test_bookmarks_have_study_root_and_branches(blank_doc):
    toc = blank_doc.get_toc()
    titles = [t[1] for t in toc]
    assert any(t.startswith("D") and t[1:4].isdigit() for t in titles)  # study id root
    assert "By Domain" in titles
    assert "By Visit" in titles
    # Form labels use "DOMAIN: Name (CODE)" form.
    assert any("(" in t and ":" in t for t in titles)


# ─── DB/Raw CRF: EDC spec-table pages must NOT be annotated ───────────────────

def test_db_spec_pages_not_annotated(db_job):
    doc = fitz.open(str(db_job.output_pdf_path))
    try:
        spec_annot = 0
        for pi in range(doc.page_count):
            t = doc[pi].get_text()
            if "Field Name" in t and "Data Type" in t and \
                    ("SAS Format" in t or "SAS Label" in t):
                spec_annot += len(_freetext_annots(doc[pi]))
        assert spec_annot == 0
    finally:
        doc.close()


# ─── Number-less CRF: Demographics resolves correctly ─────────────────────────

def test_numberless_dm_resolves(numberless_job):
    labels = {
        r.field_label.lower(): (r.sdtm_domain, r.sdtm_variable)
        for r in numberless_job.all_results if r.resolved
    }
    assert labels.get("sex") == ("DM", "SEX")
    assert labels.get("ethnicity") == ("DM", "ETHNIC")
    assert labels.get("race") == ("DM", "RACE")
