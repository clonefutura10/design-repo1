"""
Professional aCRF PDF Annotation Writer — CDISC industry-standard output.

Visual features matching real annotated CRF conventions:
- Right-margin annotations as colored text with subtle boxes
- NO separator line, NO tick marks (clean professional look)
- Colour-coded by SDTM domain (unique colour per domain)
- Stacked entries for multi-domain mappings placed SIDE BY SIDE
- Domain dataset-name headers at top-left with colored background box
- [NOT SUBMITTED] in distinct grey with dashed border
- Where-clauses on second line, same font weight
- Hierarchical PDF bookmarks: domain-class → form
- Legend page appended at the end of the output PDF
- "For Annotations see page X" on repeated form pages
- Adaptive font sizing for dense pages
- Horizontal stagger for overlapping annotations (different fields)
- Side-by-side layout for multiple mappings (same field)
- REPEATED ANNOTATIONS: Same variable at different Y positions is annotated
  each time (CDISC requirement for multi-instance fields)
"""

from __future__ import annotations

from pathlib import Path
from collections import defaultdict

import fitz  # pymupdf

from src.pdf_parser.field_identifier import CRFField
from src.resolution.models import ResolutionResult
from src.resolution.findings_qualifier import test_name_for_code
from src.utils.logging_config import get_logger

try:
    from config.settings import ANNOTATION_STYLE
except Exception:  # pragma: no cover
    class _FallbackStyle:
        use_domain_prefix = False
        title_case_headers = True
        quote_where_values = False
        emit_test_assignment = True
        render_as_content = True
    ANNOTATION_STYLE = _FallbackStyle()  # type: ignore

logger = get_logger(__name__)


# Acronyms that must stay upper-cased when Title-Casing domain full names.
_HEADER_ACRONYMS = {"ECG", "PK"}


def _title_case_name(name: str) -> str:
    """Title-Case a domain full name while preserving known acronyms.

    Capitalises every maximal alphabetic run (so '/'-joined words like
    'CONCOMITANT/PRIOR' become 'Concomitant/Prior'); tokens that are known
    acronyms (e.g. 'ECG') are kept upper-case.

    e.g. 'ECG TEST RESULTS' -> 'ECG Test Results',
         'INCLUSION/EXCLUSION CRITERIA NOT MET' -> 'Inclusion/Exclusion Criteria Not Met'.
    """
    import re

    small_words = {"or", "of", "and", "the", "in", "to", "for", "a", "an"}
    state = {"first": True}

    def _cap(m: "re.Match") -> str:
        w = m.group(0)
        is_first = state["first"]
        state["first"] = False
        if w.upper() in _HEADER_ACRONYMS:
            return w.upper()
        if not is_first and w.lower() in small_words:
            return w.lower()
        return w[0].upper() + w[1:].lower()

    return re.sub(r"[A-Za-z]+", _cap, name)


# =============================================================================
# Style Configuration
# =============================================================================

# Arial is the SDTM-MSG v2.0 recommended font (Section 3.1.2). PyMuPDF's base-14
# "helv"/"hebo" are the Helvetica/Arial-equivalent substitutes and render
# identically in every viewer.
_FONT_NAME = "helv"
_FONT_NAME_BOLD = "hebo"

# SDTM-MSG v2.0 recommends a 12-point font, allowing reduction to fit the page.
# The AZ production aCRF uses 12pt bold for domain headers and 10pt for variable
# annotations — matched here, with an automatic reduction on dense pages.
_FONT_SIZE = 9.5
_FONT_SIZE_DENSE = 8.0
_HEADER_FONT_SIZE = 11.0
_LEGEND_FONT_SIZE = 8.0

_BORDER_WIDTH = 0.6
_BOX_PADDING_X = 3.0
_BOX_PADDING_Y = 2.0
_MULTI_BOX_H_GAP = 4.0  # horizontal gap between side-by-side boxes

_ANNOTATION_X_RATIO = 0.56

_PAGE_TOP_MARGIN = 52.0
_PAGE_BOTTOM_MARGIN = 28.0
_DENSE_THRESHOLD = 14

# SDTM-MSG v2.0 (Section 3.1.2): annotation text is BLACK — bold for domain
# headers, non-bold for variable annotations. Only the box border is coloured.
_TEXT_COLOUR = (0.0, 0.0, 0.0)
_ANNOT_TEXT_COLOUR = (0.0, 0.0, 0.0)
_NOT_SUB_TEXT = (0.0, 0.0, 0.0)
_NOT_SUB_BORDER = (0.50, 0.50, 0.50)
_NOT_SUB_FILL = None  # transparent — MSG style uses no fill

_HEADER_BAR_HEIGHT = 11.0

_LINE_SPACING = 1.5

_FT_LINE_FACTOR = 1.45
_FT_SIDE_INSET = 4.0

# Horizontal stagger for overlapping annotations (different fields)
_STAGGER_SHIFT_X = -120.0

# Overlap-avoidance (SDTM-MSG v2.0 §3.1.2 pt.9 "avoid covering text" / pt.4
# "reduce font size to accommodate"):
_TEXT_CLEAR_GAP = 6.0     # gap left between CRF text and the annotation box
_MIN_ANNOT_WIDTH = 70.0   # never push the box start past (page_width - this)
_FONT_SIZE_MIN = 5.5      # smallest font when shrinking to fit the right margin

# Navigation-note style
_NOTE_FONT_SIZE = 9.0
_NOTE_FILL = (0.93, 0.95, 0.99)
_NOTE_BORDER = (0.30, 0.42, 0.62)
_NOTE_TEXT = (0.18, 0.28, 0.48)


# =============================================================================
# SDTM Domain Metadata
# =============================================================================

_DOMAIN_NAMES: dict[str, str] = {
    "AE": "ADVERSE EVENTS", "BE": "BIOSPECIMEN EVENTS",
    "CE": "CLINICAL EVENTS", "CM": "CONCOMITANT/PRIOR MEDICATIONS",
    "CO": "COMMENTS", "DD": "DEATH DETAILS",
    "DM": "DEMOGRAPHICS", "DS": "DISPOSITION",
    "EC": "EXPOSURE AS COLLECTED", "EG": "ECG TEST RESULTS",
    "EX": "EXPOSURE", "FA": "FINDINGS ABOUT EVENTS OR INTERVENTIONS",
    "FACE": "FINDINGS ABOUT – CLINICAL EVENTS",
    "FAHO": "FINDINGS ABOUT – HEALTHCARE ENCOUNTERS",
    "HO": "HEALTHCARE ENCOUNTERS",
    "IE": "INCLUSION/EXCLUSION CRITERIA NOT MET",
    "IS": "IMMUNOGENICITY SPECIMEN", "LB": "LABORATORY TEST RESULTS",
    "MB": "MICROBIOLOGY SPECIMEN", "MH": "MEDICAL HISTORY",
    "PC": "PHARMACOKINETICS CONCENTRATIONS",
    "PE": "PHYSICAL EXAMINATION", "PR": "PROCEDURES",
    "QS": "QUESTIONNAIRES", "RE": "RESPIRATORY SYSTEM FINDINGS",
    "RP": "REPRODUCTIVE SYSTEM FINDINGS", "RS": "DISEASE RESPONSE",
    "SC": "SUBJECT CHARACTERISTICS", "SU": "SUBSTANCE USE",
    "SV": "SUBJECT VISITS", "TI": "TRIAL INCLUSION / EXCLUSION",
    "TR": "TUMOR / LESION RESULTS", "TU": "TUMOR IDENTIFICATION",
    "VS": "VITAL SIGNS",
    "SUPPDM": "SUPPLEMENTAL DEMOGRAPHICS",
    "SUPPAE": "SUPPLEMENTAL ADVERSE EVENTS",
    "SUPPCM": "SUPPLEMENTAL CONCOMITANT MEDICATIONS",
    "SUPPEG": "SUPPLEMENTAL ECG TEST RESULTS",
    "SUPPFA": "SUPPLEMENTAL FINDINGS ABOUT",
    "SUPPHO": "SUPPLEMENTAL HEALTHCARE ENCOUNTERS",
    "SUPPIE": "SUPPLEMENTAL INCLUSION / EXCLUSION",
    "SUPPLB": "SUPPLEMENTAL LABORATORY TEST RESULTS",
    "SUPPMH": "SUPPLEMENTAL MEDICAL HISTORY",
    "SUPPPR": "SUPPLEMENTAL PROCEDURES",
    "SUPPSU": "SUPPLEMENTAL SUBSTANCE USE",
    "SUPPVS": "SUPPLEMENTAL VITAL SIGNS",
}

_DOMAIN_CLASSES: dict[str, list[str]] = {
    "Events": ["AE", "CE", "DD", "HO", "MH"],
    "Interventions": ["CM", "EC", "EX", "PR", "SU"],
    "Findings": ["BE", "EG", "FA", "FACE", "FAHO", "IS", "LB", "MB", "PC", "PE", "QS", "RE", "RP", "VS"],
    "Special": ["CO", "DM", "DS", "IE", "SC", "SV", "TI"],
    "Oncology": ["RS", "TR", "TU"],
}


def _domain_class(domain: str) -> str:
    d = domain.upper()
    if d.startswith("SUPP"):
        d = d[4:]
    for cls, members in _DOMAIN_CLASSES.items():
        if d in members:
            return cls
    return "Other"


def _get_domain_full_name(domain: str) -> str:
    d = domain.upper()
    name = _DOMAIN_NAMES.get(d, d)
    if getattr(ANNOTATION_STYLE, "title_case_headers", True) and name != d:
        return _title_case_name(name)
    return name


# =============================================================================
# SDTM-MSG v2.0 Colour Sequence (Section 3.1.2, point 7)
# =============================================================================
#
# The MSG specifies a fixed, colour-blindness-tested sequence to be applied to
# the domains appearing on a page (1st domain → blue, 2nd → yellow, 3rd → green,
# 4th → orange). Colours are positional per page, NOT a fixed colour per domain.
# These are the exact RGB values from the MSG sample (and the AZ production
# aCRF): the colour is used for the box BORDER; the fill is transparent.
_MSG_COLOUR_SEQUENCE: list[tuple[float, float, float]] = [
    (191 / 255, 255 / 255, 255 / 255),  # 1. BLUE   191,255,255
    (255 / 255, 255 / 255, 150 / 255),  # 2. YELLOW 255,255,150
    (150 / 255, 255 / 255, 150 / 255),  # 3. GREEN  150,255,150
    (255 / 255, 190 / 255, 155 / 255),  # 4. ORANGE 255,190,155
]


def _seq_colour(index: int) -> tuple[float, float, float]:
    """Return the MSG sequence colour for a 0-based domain position on a page."""
    return _MSG_COLOUR_SEQUENCE[index % len(_MSG_COLOUR_SEQUENCE)]


def _build_page_colour_map(domains: list[str]) -> dict[str, tuple[float, float, float]]:
    """Map each domain on a page to its positional MSG sequence colour."""
    return {dom: _seq_colour(i) for i, dom in enumerate(domains)}


# Retained for backward compatibility / the colour legend only. The live
# annotation colours now come from the positional MSG sequence above.
_DOMAIN_COLOURS: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "AE": ((0.80, 0.05, 0.05), (1.00, 0.85, 0.85)),
    "CE": ((0.75, 0.35, 0.00), (1.00, 0.90, 0.78)),
    "DD": ((0.50, 0.00, 0.00), (0.92, 0.78, 0.78)),
    "HO": ((0.85, 0.20, 0.40), (1.00, 0.84, 0.88)),
    "MH": ((0.60, 0.00, 0.30), (0.94, 0.80, 0.86)),
    "CM": ((0.00, 0.52, 0.00), (0.82, 0.96, 0.82)),
    "EC": ((0.00, 0.50, 0.45), (0.78, 0.95, 0.93)),
    "EX": ((0.35, 0.55, 0.00), (0.88, 0.94, 0.76)),
    "PR": ((0.10, 0.38, 0.10), (0.80, 0.92, 0.80)),
    "SU": ((0.00, 0.42, 0.30), (0.78, 0.93, 0.88)),
    "BE": ((0.00, 0.25, 0.70), (0.80, 0.86, 1.00)),
    "EG": ((0.45, 0.00, 0.70), (0.90, 0.80, 1.00)),
    "FA": ((0.00, 0.40, 0.60), (0.78, 0.90, 0.96)),
    "FACE": ((0.00, 0.55, 0.55), (0.78, 0.94, 0.94)),
    "FAHO": ((0.20, 0.30, 0.60), (0.82, 0.85, 0.96)),
    "IS": ((0.30, 0.10, 0.55), (0.86, 0.80, 0.94)),
    "LB": ((0.00, 0.30, 0.55), (0.78, 0.87, 0.96)),
    "MB": ((0.10, 0.45, 0.55), (0.80, 0.91, 0.94)),
    "PC": ((0.00, 0.50, 0.50), (0.78, 0.94, 0.94)),
    "PE": ((0.25, 0.25, 0.65), (0.84, 0.84, 0.98)),
    "QS": ((0.50, 0.20, 0.50), (0.92, 0.82, 0.92)),
    "RE": ((0.00, 0.35, 0.70), (0.78, 0.88, 1.00)),
    "RP": ((0.55, 0.00, 0.55), (0.93, 0.78, 0.93)),
    "VS": ((0.00, 0.45, 0.75), (0.78, 0.90, 1.00)),
    "CO": ((0.40, 0.40, 0.00), (0.92, 0.92, 0.76)),
    "DM": ((0.55, 0.00, 0.68), (0.92, 0.78, 0.96)),
    "DS": ((0.00, 0.45, 0.20), (0.78, 0.93, 0.84)),
    "IE": ((0.60, 0.30, 0.00), (0.96, 0.88, 0.76)),
    "SC": ((0.50, 0.10, 0.40), (0.92, 0.80, 0.90)),
    "SV": ((0.20, 0.20, 0.55), (0.84, 0.84, 0.94)),
    "TI": ((0.45, 0.25, 0.00), (0.92, 0.86, 0.76)),
    "RS": ((0.65, 0.00, 0.20), (0.96, 0.78, 0.84)),
    "TR": ((0.70, 0.25, 0.00), (0.98, 0.86, 0.76)),
    "TU": ((0.55, 0.00, 0.40), (0.94, 0.78, 0.88)),
}

_DEFAULT_BORDER = (0.35, 0.35, 0.35)
_DEFAULT_FILL = (0.96, 0.96, 0.96)


def _get_domain_colours(domain: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    d = domain.upper()
    if d in _DOMAIN_COLOURS:
        return _DOMAIN_COLOURS[d]
    if d.startswith("SUPP"):
        base = d[4:]
        if base in _DOMAIN_COLOURS:
            return _DOMAIN_COLOURS[base]
    return (_DEFAULT_BORDER, _DEFAULT_FILL)


# =============================================================================
# Annotation Entry Builder
# =============================================================================

def _build_annotations_list(result: ResolutionResult) -> list[dict]:
    """
    Return a list of annotation dicts for a field.
    """
    annotations: list[dict] = []

    if result.is_not_submitted:
        annotations.append({
            "text": "[NOT SUBMITTED]",
            "domain": "",
            "is_not_submitted": True,
            "is_supp": False,
            "where_clause": "",
            "is_derived": getattr(result, "is_derived", False),
        })
        return annotations

    if not result.sdtm_domain or not result.sdtm_variable:
        return annotations

    use_prefix = getattr(ANNOTATION_STYLE, "use_domain_prefix", False)
    supp_fmt = getattr(ANNOTATION_STYLE, "supp_format", "in")
    domain = result.sdtm_domain.upper()
    is_supp = result.is_supplemental
    base_domain = domain[4:] if domain.startswith("SUPP") else domain

    if is_supp:
        prefix = domain if domain.startswith("SUPP") else f"SUPP{domain}"
        if supp_fmt == "qval":
            # AZ house style: ``SUPPxx.QVAL where QNAM = <var>``.
            primary_text = f"{prefix}.QVAL"
            primary_qnam = result.sdtm_variable
        else:
            # MSG v2.0 §3.1.2 pt.5: ``<QNAM> in SUPPxx`` (e.g. AEACN01 in SUPPAE).
            primary_text = f"{result.sdtm_variable} in {prefix}"
            primary_qnam = ""
    elif use_prefix:
        primary_text = f"{domain}.{result.sdtm_variable}"
        primary_qnam = ""
    else:
        # AZ house style: standalone variable name, no DOMAIN. prefix.
        primary_text = result.sdtm_variable
        primary_qnam = ""

    if result.codelist_code and not is_supp:
        primary_text += f" ({result.codelist_code})"

    from collections import OrderedDict
    groups: OrderedDict[tuple[str, bool, str], list[str]] = OrderedDict()
    groups[(base_domain, is_supp, primary_qnam)] = [primary_text]

    for mapping in getattr(result, "additional_mappings", None) or []:
        add_domain = (mapping.get("domain") or mapping.get("sdtm_domain", "")).upper()
        add_variable = mapping.get("variable") or mapping.get("sdtm_variable", "")
        add_codelist = mapping.get("codelist") or mapping.get("codelist_code", "")
        add_is_supp = mapping.get("is_supp", False) or mapping.get("is_supplemental", False)

        if not add_domain or not add_variable:
            continue

        if add_is_supp:
            pfx = add_domain if add_domain.startswith("SUPP") else f"SUPP{add_domain}"
            if supp_fmt == "qval":
                add_text = f"{pfx}.QVAL"
                add_qnam = add_variable
            else:
                add_text = f"{add_variable} in {pfx}"
                add_qnam = ""
        elif use_prefix:
            add_text = f"{add_domain}.{add_variable}"
            add_qnam = ""
        else:
            add_text = add_variable
            add_qnam = ""

        if add_codelist and not add_is_supp:
            add_text += f" ({add_codelist})"

        ann_base = add_domain[4:] if add_domain.startswith("SUPP") else add_domain
        key = (ann_base, add_is_supp, add_qnam)
        if key not in groups:
            groups[key] = []
        groups[key].append(add_text)

    testcd_where = getattr(result, "where_clause", "") or ""
    is_derived = getattr(result, "is_derived", False)
    value_decode = getattr(result, "value_decode", "") or ""

    emit_test = getattr(ANNOTATION_STYLE, "emit_test_assignment", True)

    for grp_index, ((grp_domain, grp_is_supp, grp_qnam), texts) in enumerate(groups.items()):
        combined_text = " / ".join(texts)
        if grp_is_supp:
            wc = f"QNAM = {grp_qnam}" if grp_qnam else ""
        elif grp_domain == base_domain and not is_supp:
            wc = testcd_where
        else:
            wc = ""

        # AZ-style companion test assignment (e.g. "VSTEST = Weight") for the
        # primary Findings result so both the test name and the result variable
        # are documented, per SDTM-MSG Findings annotation guidance.
        test_assign = ""
        if emit_test and wc and not grp_is_supp:
            test_assign = _test_assignment_for(grp_domain, wc)

        annotations.append({
            "text": combined_text,
            "domain": grp_domain,
            "is_not_submitted": False,
            "is_supp": grp_is_supp,
            "where_clause": wc,
            "is_derived": is_derived,
            "value_decode": value_decode if grp_index == 0 else "",
            "test_assign": test_assign,
        })

    return annotations


def _entry_box_width(entry: dict, fs: float) -> float:
    """Width of an annotation box for ``entry`` at font size ``fs``.

    Mirrors the per-line width computation in the draw loop so placement and
    font-fit logic agree with what is actually rendered.
    """
    tw = fitz.get_text_length(entry.get("text", "") or "", fontname=_FONT_NAME, fontsize=fs)
    ta = entry.get("test_assign", "") or ""
    if ta:
        tw = max(tw, fitz.get_text_length(ta, fontname=_FONT_NAME, fontsize=fs))
    wc = entry.get("where_clause", "") or ""
    if wc:
        kw = getattr(ANNOTATION_STYLE, "conditional_keyword", "when")
        tw = max(tw, fitz.get_text_length(f"{kw} {wc}", fontname=_FONT_NAME, fontsize=fs))
    vd = entry.get("value_decode", "") or ""
    if vd:
        tw = max(tw, fitz.get_text_length(f"({vd})", fontname=_FONT_NAME, fontsize=fs))
    return tw + 2 * _BOX_PADDING_X + _FT_SIDE_INSET


def _test_assignment_for(domain: str, where_clause: str) -> str:
    """Build a ``--TEST = <Name>`` string from a TESTCD where-clause, if known.

    Returns '' when the domain has no TEST variable or the code is unknown,
    so generic/placeholder grids are never given a spurious test name.
    """
    import re
    m = re.match(r"\s*([A-Z]+)TESTCD\s*=\s*\"?([A-Za-z0-9_]+)\"?", where_clause or "")
    if not m:
        return ""
    dom, code = m.group(1), m.group(2)
    name = test_name_for_code(dom, code)
    if not name:
        return ""
    return f"{dom}TEST = {name}"


# =============================================================================
# Page Domain Helpers
# =============================================================================

def _get_all_domains_for_page(results_on_page: list[ResolutionResult], form_code: str = "") -> list[str]:
    """Return unique base domains for a page, ordered by frequency."""
    counts: dict[str, int] = defaultdict(int)

    if form_code:
        try:
            from src.resolution.tier0_rules import _get_domain_for_form
            mapped = _get_domain_for_form(form_code)
            if mapped:
                counts[mapped] += 1000
        except Exception:
            pass

    for r in results_on_page:
        if not r.resolved or r.is_not_submitted:
            continue
        if r.sdtm_domain:
            d = r.sdtm_domain.upper()
            d = d[4:] if d.startswith("SUPP") else d
            counts[d] += 1
        for m in getattr(r, "additional_mappings", None) or []:
            ad = (m.get("domain") or m.get("sdtm_domain", "")).upper()
            if ad:
                ad = ad[4:] if ad.startswith("SUPP") else ad
                counts[ad] += 1

    return [d for d, _ in sorted(counts.items(), key=lambda x: -x[1])]


# =============================================================================
# Domain Header — top-LEFT of page, WITH colored background box
# =============================================================================

_DOMAIN_HEADER_LEFT_X = 36.0
_DOMAIN_HEADER_Y = 62.0


def _draw_box_content(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    fontsize: float,
    fontname: str,
    text_color: tuple,
    fill_color: tuple,
    border_color: tuple,
    border_width: float,
    dashed: bool,
) -> None:
    """Draw a filled, bordered box + (multi-line) text on the page content
    stream so colours render in every PDF viewer (browser and Adobe alike)."""
    # Filled, bordered rectangle.
    page.draw_rect(
        rect,
        color=border_color,
        fill=fill_color,
        width=border_width,
        dashes="[2 2] 0" if dashed else None,
        overlay=True,
    )

    # Lay out each text line from the top of the box.
    lines = text.split("\n")
    line_h = fontsize * _FT_LINE_FACTOR
    x = rect.x0 + _BOX_PADDING_X
    # Baseline of the first line (insert_text anchors at the baseline).
    y = rect.y0 + _BOX_PADDING_Y + fontsize
    for line in lines:
        if y > rect.y1 + 1:
            break
        try:
            page.insert_text(
                fitz.Point(x, y),
                line,
                fontsize=fontsize,
                fontname=fontname,
                color=text_color,
                overlay=True,
            )
        except Exception:
            pass
        y += line_h


def _freetext(
    page: fitz.Page,
    rect: fitz.Rect,
    text: str,
    fontsize: float,
    fontname: str,
    text_color: tuple,
    fill_color: tuple,
    border_color: tuple,
    border_width: float = _BORDER_WIDTH,
    dashed: bool = False,
) -> None:
    """
    Render an annotation box + text.

    When ``ANNOTATION_STYLE.render_as_content`` is enabled (default) the box and
    text are drawn directly onto the page content stream. FreeText annotation
    appearance streams (fill/border colours) are frequently dropped by
    browser-based PDF viewers (pdf.js / pdfium) even though Adobe Acrobat
    renders them — drawing on the content stream guarantees the colours appear
    identically in every viewer.
    """
    if getattr(ANNOTATION_STYLE, "render_as_content", True):
        _draw_box_content(
            page, rect, text, fontsize, fontname,
            text_color, fill_color, border_color, border_width, dashed,
        )
        return

    try:
        annot = page.add_freetext_annot(
            rect,
            text,
            fontsize=fontsize,
            fontname=fontname,
            text_color=text_color,
            fill_color=fill_color,
            align=fitz.TEXT_ALIGN_LEFT,
        )
    except Exception:
        page.draw_rect(rect, color=text_color, fill=fill_color, width=border_width,
                       dashes="[2 2] 0" if dashed else None, overlay=True)
        page.insert_text(fitz.Point(rect.x0 + _BOX_PADDING_X, rect.y1 - _BOX_PADDING_Y),
                         text, fontsize=fontsize, fontname=fontname, color=text_color)
        return

    try:
        if dashed:
            annot.set_border(width=border_width, dashes=[2, 2])
        else:
            annot.set_border(width=border_width)
    except Exception:
        pass
    try:
        annot.update()
    except Exception:
        pass


def _draw_domain_name_top_left(
    page: fitz.Page,
    domains: list[str],
    colour_map: dict[str, tuple[float, float, float]] | None = None,
) -> None:
    """Draw domain-name header boxes at the top-left of the page.

    Per SDTM-MSG v2.0: domain annotations are BLACK BOLD text in the format
    ``XX = Domain Label`` (AZ house style), inside a box whose BORDER carries
    the domain's positional MSG sequence colour; the fill is transparent.
    """
    if not domains:
        return

    colour_map = colour_map or _build_page_colour_map(domains)
    fmt = getattr(ANNOTATION_STYLE, "domain_header_format", "paren")
    y = _DOMAIN_HEADER_Y
    for domain in domains:
        full_name = _get_domain_full_name(domain)
        # MSG v2.0 §3.1.2 pt.5: "DM (Demographics)". "equals" is the legacy
        # v1.0 / AZ form "DM = Demographics".
        if fmt == "equals":
            label_text = f"{domain} = {full_name}"
        else:
            label_text = f"{domain} ({full_name})"
        border_c = colour_map.get(domain) or _seq_colour(0)

        tw = fitz.get_text_length(label_text, fontname=_FONT_NAME_BOLD, fontsize=_HEADER_FONT_SIZE)
        box_h = _HEADER_FONT_SIZE * _FT_LINE_FACTOR + 2 * _BOX_PADDING_Y
        box_rect = fitz.Rect(
            _DOMAIN_HEADER_LEFT_X - 2,
            y - box_h + 1,
            _DOMAIN_HEADER_LEFT_X + tw + 2 * _BOX_PADDING_X + _FT_SIDE_INSET,
            y + 2,
        )
        _freetext(
            page, box_rect, label_text,
            fontsize=_HEADER_FONT_SIZE, fontname=_FONT_NAME_BOLD,
            text_color=_TEXT_COLOUR, fill_color=None, border_color=border_c,
            border_width=1.0,
        )
        y += box_h + 2.0


def _draw_note(page: fitz.Page, text: str, ann_x: float, y_top: float) -> None:
    """Draw a navigation-note FreeText box."""
    tw = fitz.get_text_length(text, fontname=_FONT_NAME_BOLD, fontsize=_NOTE_FONT_SIZE)
    h = _NOTE_FONT_SIZE * _FT_LINE_FACTOR + 2 * _BOX_PADDING_Y
    rect = fitz.Rect(ann_x, y_top, ann_x + tw + 2 * _BOX_PADDING_X + _FT_SIDE_INSET, y_top + h)
    _freetext(page, rect, text, fontsize=_NOTE_FONT_SIZE, fontname=_FONT_NAME_BOLD,
              text_color=_NOTE_TEXT, fill_color=_NOTE_FILL, border_color=_NOTE_BORDER,
              border_width=0.7)


def _draw_see_page_reference(page: fitz.Page, first_pages: list[int], page_height: float, ann_x: float) -> None:
    """Write 'For Annotations see page X' as a navigation note at the bottom."""
    if not first_pages:
        return

    page_nums = [str(p + 1) for p in first_pages]
    if len(page_nums) <= 3:
        ref_text = f"For Annotations see page {' · '.join(page_nums)}"
    else:
        ref_text = f"For Annotations see page {page_nums[0]} – {page_nums[-1]}"

    h = _NOTE_FONT_SIZE * _FT_LINE_FACTOR + 2 * _BOX_PADDING_Y
    _draw_note(page, ref_text, ann_x, _PAGE_TOP_MARGIN)


def _draw_continued_from_page(page: fitz.Page, prev_page_num: int, ann_x: float) -> None:
    """Write 'Continued from page X' near the top of the column."""
    _draw_note(page, f"Continued from page {prev_page_num}", ann_x, 72.0)


# =============================================================================
# Placement Tracker — Dedup + Horizontal Stagger on Overlap
# =============================================================================

_DEDUP_Y_TOLERANCE = 3.0


class _PlacementTracker:
    """
    Tracks placed annotations for:
    1. Deduplication (same text at same Y = skip)
    2. Horizontal stagger (when different-field annotations overlap vertically)
    """

    def __init__(self):
        self._placed: dict[int, list[tuple[str, float]]] = defaultdict(list)
        self._occupied: dict[int, list[tuple[float, float]]] = defaultdict(list)

    def is_duplicate(self, page_idx: int, text: str, y_pos: float) -> bool:
        """Check if this exact text was already placed at this Y position."""
        for placed_text, placed_y in self._placed[page_idx]:
            if placed_text == text and abs(placed_y - y_pos) < _DEDUP_Y_TOLERANCE:
                return True
        self._placed[page_idx].append((text, y_pos))
        return False

    def get_x_offset(self, page_idx: int, box_top: float, box_bottom: float) -> float:
        """
        If this box's vertical range overlaps with an existing annotation
        from a DIFFERENT field, return a LEFT shift so both are readable.
        """
        for (ot, ob) in self._occupied[page_idx]:
            if box_top < ob and box_bottom > ot:
                return _STAGGER_SHIFT_X
        return 0.0

    def find_free_y(
        self, page_idx: int, top: float, bottom: float, max_bottom: float
    ) -> float:
        """
        Return a (possibly lowered) box-top so the box does not overlap an
        already-placed annotation. Nudges DOWN into free whitespace rather than
        shifting left over CRF text (SDTM-MSG v2.0 §3.1.2 pt.9). If no free slot
        fits above ``max_bottom``, returns the original top unchanged.
        """
        h = bottom - top
        cur_top = top
        guard = 0
        moved = True
        while moved and guard < 300:
            moved = False
            guard += 1
            for (ot, ob) in self._occupied[page_idx]:
                if cur_top < ob and (cur_top + h) > ot:
                    cur_top = ob + 1.5
                    moved = True
                    break
        if cur_top + h > max_bottom:
            return top
        return cur_top

    def mark_occupied(self, page_idx: int, box_top: float, box_bottom: float) -> None:
        """Record the vertical span of a placed annotation."""
        self._occupied[page_idx].append((box_top, box_bottom))


# =============================================================================
# Legend Page
# =============================================================================

def _append_legend_page(doc: fitz.Document, page_width: float, page_height: float):
    """Append an annotation-conventions legend page following SDTM-MSG v2.0."""
    page = doc.new_page(width=page_width, height=page_height)

    page.insert_text(fitz.Point(36, 44), "Annotation Conventions (SDTM-MSG v2.0)",
                     fontsize=14, fontname=_FONT_NAME_BOLD, color=(0.0, 0.0, 0.0))
    page.insert_text(fitz.Point(36, 56),
                     "Annotations follow the CDISC SDTM Metadata Submission Guidelines v2.0, Section 3.1.2.",
                     fontsize=8, fontname=_FONT_NAME, color=(0.40, 0.40, 0.40))
    page.draw_line(fitz.Point(36, 60), fitz.Point(page_width - 36, 60),
                   color=(0.70, 0.70, 0.70), width=0.5)

    x = 38.0
    box_w, box_h = 26.0, 12.0
    row_height = 20.0
    y = 84.0

    page.insert_text(fitz.Point(x, y), "Domain colour sequence (applied per page)",
                     fontsize=9, fontname=_FONT_NAME_BOLD, color=(0.0, 0.0, 0.0))
    y += row_height
    seq_labels = [
        "1st domain on page", "2nd domain on page",
        "3rd domain on page", "4th domain on page",
    ]
    rgb_labels = ["191, 255, 255", "255, 255, 150", "150, 255, 150", "255, 190, 155"]
    for i, colour in enumerate(_MSG_COLOUR_SEQUENCE):
        swatch = fitz.Rect(x, y - box_h + 1, x + box_w, y + 1)
        page.draw_rect(swatch, color=colour, fill=None, width=1.0)
        page.insert_text(fitz.Point(x + box_w + 8, y),
                         f"{seq_labels[i]}   (RGB {rgb_labels[i]})",
                         fontsize=8.5, fontname=_FONT_NAME, color=(0.0, 0.0, 0.0))
        y += row_height

    y += row_height * 0.4
    page.insert_text(fitz.Point(x, y), "Annotation styles", fontsize=9,
                     fontname=_FONT_NAME_BOLD, color=(0.0, 0.0, 0.0))
    y += row_height

    # Domain header sample
    page.insert_text(fitz.Point(x, y), "XX = Domain Label",
                     fontsize=9, fontname=_FONT_NAME_BOLD, color=(0.0, 0.0, 0.0))
    page.insert_text(fitz.Point(x + 160, y),
                     "Domain annotation — black, bold (XX = Domain Label).",
                     fontsize=8.5, fontname=_FONT_NAME, color=(0.0, 0.0, 0.0))
    y += row_height
    page.insert_text(fitz.Point(x, y), "VARIABLE",
                     fontsize=9, fontname=_FONT_NAME, color=(0.0, 0.0, 0.0))
    page.insert_text(fitz.Point(x + 160, y),
                     "Variable annotation — black, non-bold, coloured box border.",
                     fontsize=8.5, fontname=_FONT_NAME, color=(0.0, 0.0, 0.0))
    y += row_height
    ns_rect = fitz.Rect(x, y - box_h + 1, x + box_w + 40, y + 1)
    page.draw_rect(ns_rect, color=_NOT_SUB_BORDER, fill=None, width=0.8, dashes="[2 2] 0")
    page.insert_text(fitz.Point(x + box_w + 48, y),
                     "Dashed border — [NOT SUBMITTED] or non-collected / derived variable.",
                     fontsize=8.5, fontname=_FONT_NAME, color=(0.0, 0.0, 0.0))
    y += row_height

    page.draw_line(fitz.Point(36, page_height - 56), fitz.Point(page_width - 36, page_height - 56),
                   color=(0.75, 0.75, 0.75), width=0.4)
    notes = [
        "Variables and dataset codes are capitalised; multiple variables are separated by \" / \".",
        "Supplemental Qualifier variables are annotated as SUPPxx.QVAL where QNAM = <variable>.",
        "Findings use the \"--ORRES where --TESTCD = <value>\" format; explicit values are not quoted.",
        "This aCRF was generated automatically — verify all annotations against the study SDTM specification.",
    ]
    ny = page_height - 46
    for n in notes:
        page.insert_text(fitz.Point(36, ny), n, fontsize=7,
                         fontname=_FONT_NAME, color=(0.45, 0.45, 0.45))
        ny += 10


# =============================================================================
# Hierarchical Bookmark Builder
# =============================================================================

def _build_toc(
    form_first_page: dict[str, tuple[int, str]],
    form_domains: dict[str, str],
    form_visits: dict[str, list[tuple[str, int]]] | None = None,
) -> list[list]:
    """Build a dual bookmark hierarchy."""
    toc: list[list] = []

    # Branch 1: By Topic
    class_domain_forms: dict[str, dict[str, list[tuple[str, int]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for form_code, (page_idx, _) in sorted(form_first_page.items(), key=lambda x: x[1][0]):
        domain = form_domains.get(form_code, "")
        cls = _domain_class(domain) if domain else "Other"
        class_domain_forms[cls][domain or "??"].append((form_code, page_idx))

    topic_first_page = min(
        (pg for forms in class_domain_forms.values() for fl in forms.values() for _, pg in fl),
        default=0,
    )
    toc.append([1, "CRFs by Topic", topic_first_page + 1])
    class_order = list(_DOMAIN_CLASSES.keys()) + ["Other"]
    for cls in class_order:
        if cls not in class_domain_forms:
            continue
        toc.append([2, cls, list(class_domain_forms[cls].values())[0][0][1] + 1])
        for domain, forms in sorted(class_domain_forms[cls].items(), key=lambda x: x[0]):
            full = _get_domain_full_name(domain)
            toc.append([3, f"{domain} — {full}", forms[0][1] + 1])
            for form_code, pg in forms:
                toc.append([4, form_code, pg + 1])

    # Branch 2: By Visit
    if form_visits:
        visit_entries: dict[str, list[tuple[str, int]]] = defaultdict(list)
        visit_first_page: dict[str, int] = {}
        for form_code, occurrences in form_visits.items():
            for visit, page_idx in occurrences:
                if not visit:
                    continue
                visit_entries[visit].append((form_code, page_idx))
                if visit not in visit_first_page or page_idx < visit_first_page[visit]:
                    visit_first_page[visit] = page_idx

        if visit_entries:
            branch_first = min(visit_first_page.values())
            toc.append([1, "CRFs by Visit", branch_first + 1])
            for visit in sorted(visit_first_page, key=lambda v: visit_first_page[v]):
                forms = sorted(visit_entries[visit], key=lambda x: x[1])
                toc.append([2, visit, visit_first_page[visit] + 1])
                seen_forms: set[str] = set()
                for form_code, pg in forms:
                    if form_code in seen_forms:
                        continue
                    seen_forms.add(form_code)
                    toc.append([3, form_code, pg + 1])

    return toc


# =============================================================================
# Main annotate_pdf function
# =============================================================================

def _form_identity(field: CRFField) -> str:
    """
    Identity used to group repeat instances of the SAME form across visits.
    Uses form_code + form_name to avoid conflating distinct forms.
    """
    fc = (field.form_code or "").strip().upper()
    fn = (getattr(field, "form_name", "") or "").strip().lower()
    return f"{fc}|{fn}" if (fc or fn) else ""


def annotate_pdf(
    input_pdf_path: Path,
    output_pdf_path: Path,
    results: list[ResolutionResult],
    fields: list[CRFField],
    font_size: float = _FONT_SIZE,
) -> dict:
    """Write industry-standard aCRF annotations onto a blank CRF PDF."""
    if len(results) != len(fields):
        raise ValueError(f"results ({len(results)}) and fields ({len(fields)}) length mismatch")

    doc = fitz.open(str(input_pdf_path))

    stats: dict = {
        "total_annotations": 0,
        "pages_annotated": set(),
        "not_submitted": 0,
        "skipped_no_position": 0,
        "duplicates_skipped": 0,
        "multi_domain_fields": 0,
    }

    tracker = _PlacementTracker()

    # Pre-group by page
    page_results: dict[int, list[ResolutionResult]] = defaultdict(list)
    page_form_codes: dict[int, set[str]] = defaultdict(set)
    form_all_pages: dict[str, list[int]] = defaultdict(list)

    for field, result in zip(fields, results):
        pi = field.page_index
        if pi is not None:
            page_results[pi].append(result)
            if field.form_code:
                page_form_codes[pi].add(field.form_code)
            fid = _form_identity(field)
            if fid and pi not in form_all_pages[fid]:
                form_all_pages[fid].append(pi)

    # Identify first instance pages per form identity
    _INSTANCE_GAP = 3
    form_first_instance_pages: dict[str, set[int]] = {}
    for fid, pages in form_all_pages.items():
        pages_sorted = sorted(set(pages))
        first: list[int] = []
        for p in pages_sorted:
            if not first or p - first[-1] <= _INSTANCE_GAP:
                first.append(p)
            else:
                break
        form_first_instance_pages[fid] = set(first)

    form_see_pages: dict[str, set[int]] = {
        fid: set(ps for ps in pages if ps not in form_first_instance_pages[fid])
        for fid, pages in form_all_pages.items()
    }

    # Track "Continued from page X"
    form_continued_from: dict[str, dict[int, int]] = {}
    for fid, pages in form_all_pages.items():
        first_pages = sorted(form_first_instance_pages[fid])
        continued: dict[int, int] = {}
        for i in range(1, len(first_pages)):
            if first_pages[i] - first_pages[i - 1] <= 1:
                continued[first_pages[i]] = first_pages[i - 1]
        form_continued_from[fid] = continued

    page_ann_count: dict[int, int] = defaultdict(int)
    for field, result in zip(fields, results):
        pi = field.page_index
        if pi is None:
            continue
        fid = _form_identity(field)
        if fid and pi in form_see_pages.get(fid, set()):
            continue
        if result.resolved or result.is_not_submitted:
            page_ann_count[pi] += 1

    form_first_page: dict[str, tuple[int, str]] = {}
    form_primary_domain: dict[str, str] = {}
    form_visits: dict[str, list[tuple[str, int]]] = defaultdict(list)
    _seen_visit_form: set[tuple[str, str]] = set()
    for field, result in zip(fields, results):
        fc = field.form_code
        if fc and fc not in form_first_page and field.page_index is not None:
            form_first_page[fc] = (field.page_index, fc)
        if fc and fc not in form_primary_domain and result.sdtm_domain:
            d = result.sdtm_domain.upper()
            form_primary_domain[fc] = d[4:] if d.startswith("SUPP") else d
        visit = getattr(field, "folder", "") or ""
        if fc and visit and field.page_index is not None:
            key = (fc, visit)
            if key not in _seen_visit_form:
                _seen_visit_form.add(key)
                form_visits[fc].append((visit, field.page_index))

    # Precompute the positional MSG colour for every domain on every page so
    # the header box and each field annotation share a consistent colour.
    page_colour_maps: dict[int, dict[str, tuple[float, float, float]]] = {}
    for pi in page_results:
        fc_set = page_form_codes.get(pi, set())
        page_fc = next(iter(fc_set)) if len(fc_set) == 1 else ""
        doms = _get_all_domains_for_page(page_results.get(pi, []), form_code=page_fc)
        page_colour_maps[pi] = _build_page_colour_map(doms)

    # Precompute the CRF's own text spans for every page to be annotated (BEFORE
    # any annotation is drawn, so we capture only the blank-CRF text). Used to
    # place annotation boxes in whitespace to the right of the CRF text rather
    # than over it (SDTM-MSG v2.0 §3.1.2 pt.9).
    page_text_spans: dict[int, list[tuple[float, float, float, float]]] = {}
    for pi in page_results:
        spans: list[tuple[float, float, float, float]] = []
        try:
            for blk in doc[pi].get_text("dict").get("blocks", []):
                if blk.get("type") != 0:
                    continue
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        if not sp.get("text", "").strip():
                            continue
                        bx0, by0, bx1, by1 = sp["bbox"]
                        spans.append((bx0, by0, bx1, by1))
        except Exception:
            pass
        page_text_spans[pi] = spans

    domain_header_written: set[int] = set()
    see_page_written: set[str] = set()

    for field, result in zip(fields, results):
        if not result.resolved and not result.is_not_submitted:
            continue

        page_idx = field.page_index
        y = field.y
        fc = field.form_code or ""
        fid = _form_identity(field)

        if page_idx is None or y is None or y == 0.0:
            stats["skipped_no_position"] += 1
            continue

        page = doc[page_idx]
        pw = page.rect.width
        ph = page.rect.height
        ann_x = pw * _ANNOTATION_X_RATIO

        # Domain name at top-LEFT with colored box (once per page)
        if page_idx not in domain_header_written:
            domain_header_written.add(page_idx)
            fc_set = page_form_codes.get(page_idx, set())
            page_fc = next(iter(fc_set)) if len(fc_set) == 1 else fc
            page_doms = _get_all_domains_for_page(
                page_results.get(page_idx, []), form_code=page_fc
            )
            if page_doms:
                _draw_domain_name_top_left(
                    page, page_doms, page_colour_maps.get(page_idx)
                )
            # "Continued from page X" on subsequent pages of multi-page form
            if fid:
                prev_idx = form_continued_from.get(fid, {}).get(page_idx)
                if prev_idx is not None:
                    _draw_continued_from_page(page, prev_idx + 1, ann_x)

        # "For Annotations see page X" for repeat-visit pages
        if fid and page_idx in form_see_pages.get(fid, set()):
            see_key = f"{fid}_{page_idx}"
            if see_key not in see_page_written:
                see_page_written.add(see_key)
                first_inst = sorted(form_first_instance_pages.get(fid, []))
                _draw_see_page_reference(page, first_inst, ph, ann_x)
            continue

        eff_fs = _FONT_SIZE_DENSE if page_ann_count.get(page_idx, 0) > _DENSE_THRESHOLD else font_size

        ann_entries = _build_annotations_list(result)
        if not ann_entries:
            continue

        if len(ann_entries) > 1:
            stats["multi_domain_fields"] += 1

        def _entry_height(entry: dict) -> float:
            n_lines = 1
            if entry.get("test_assign"):
                n_lines += 1
            if entry.get("where_clause"):
                n_lines += 1
            if entry.get("value_decode"):
                n_lines += 1
            return n_lines * (eff_fs * _FT_LINE_FACTOR) + 2 * _BOX_PADDING_Y

        # ─── PLACEMENT: Direct at field Y, clamped to page bounds ───
        slot_y = max(_PAGE_TOP_MARGIN + _entry_height(ann_entries[0]), min(y, ph - _PAGE_BOTTOM_MARGIN))

        # ─── Determine max height across all entries (for overlap tracking) ───
        max_entry_h = max(_entry_height(e) for e in ann_entries)
        box_top_for_field = slot_y - eff_fs - _BOX_PADDING_Y
        box_bottom_for_field = box_top_for_field + max_entry_h

        # ─── Place in the row's whitespace GAP, not over CRF text (MSG pt.9) ───
        # Look at the blank-CRF text overlapping this box's vertical band, find
        # the empty horizontal gaps at/after the annotation column, and choose
        # the earliest gap wide enough for the box (keeping a consistent column
        # per MSG pt.1a). If nothing fits, the widest gap is used and the font is
        # reduced to fit it (MSG pt.4) so the box never spills off the page.
        spans = page_text_spans.get(page_idx, [])
        floor_x = ann_x
        right_limit = pw - 8.0
        band_intervals = sorted(
            (sx0, sx1) for (sx0, sy0, sx1, sy1) in spans
            if sy0 < box_bottom_for_field and sy1 > box_top_for_field and sx1 > floor_x
        )
        gaps: list[tuple[float, float]] = []
        cursor = floor_x
        for (sx0, sx1) in band_intervals:
            if sx0 - cursor > 8.0:
                gaps.append((cursor + _TEXT_CLEAR_GAP if cursor > floor_x else cursor, sx0 - 2.0))
            cursor = max(cursor, sx1)
        if right_limit - cursor > 8.0:
            gaps.append((cursor + _TEXT_CLEAR_GAP if cursor > floor_x else cursor, right_limit))

        needed_w = max(_entry_box_width(e, eff_fs) for e in ann_entries)

        base_x = floor_x
        avail_w = right_limit - floor_x
        if gaps:
            fitting = [g for g in gaps if (g[1] - g[0]) >= needed_w]
            chosen = min(fitting, key=lambda g: g[0]) if fitting else max(gaps, key=lambda g: g[1] - g[0])
            base_x = chosen[0]
            avail_w = chosen[1] - chosen[0]

        base_x = min(max(36.0, base_x), pw - _MIN_ANNOT_WIDTH)

        # ─── Fit font to the chosen gap (MSG pt.4) ───
        if needed_w > avail_w and avail_w > 24.0:
            eff_fs = max(_FONT_SIZE_MIN, eff_fs * (avail_w / needed_w))
            max_entry_h = max(_entry_height(e) for e in ann_entries)
            box_top_for_field = slot_y - eff_fs - _BOX_PADDING_Y
            box_bottom_for_field = box_top_for_field + max_entry_h

        # ─── Nudge DOWN (not left) to avoid covering another annotation ───
        free_top = tracker.find_free_y(
            page_idx, box_top_for_field, box_bottom_for_field, ph - _PAGE_BOTTOM_MARGIN
        )
        if free_top != box_top_for_field:
            shift = free_top - box_top_for_field
            slot_y += shift
            box_top_for_field += shift
            box_bottom_for_field += shift

        # ─── Draw entries SIDE BY SIDE horizontally ───
        x_cursor = base_x
        any_drawn = False

        for entry in ann_entries:
            ann_text = entry["text"]
            where_clause = entry.get("where_clause", "") or ""
            value_decode = entry.get("value_decode", "") or ""
            test_assign = entry.get("test_assign", "") or ""
            is_derived = entry.get("is_derived", False)

            if not ann_text:
                continue

            if tracker.is_duplicate(page_idx, ann_text + where_clause, slot_y):
                stats["duplicates_skipped"] += 1
                continue

            this_h = _entry_height(entry)

            # SDTM-MSG v2.0: variable annotations are BLACK, non-bold text in a
            # box whose BORDER carries the domain's positional colour; the fill
            # is transparent. Non-collected / derived annotations get a dashed
            # border (MSG Section 3.1.2, point 8 + Findings guidance).
            if entry["is_not_submitted"]:
                border_c = _NOT_SUB_BORDER
                fill_c = _NOT_SUB_FILL
                text_c = _NOT_SUB_TEXT
                font_n = _FONT_NAME
                use_dash = True
                stats["not_submitted"] += 1
            else:
                border_c = page_colour_maps.get(page_idx, {}).get(
                    entry["domain"]
                ) or _seq_colour(0)
                fill_c = None
                text_c = _ANNOT_TEXT_COLOUR
                font_n = _FONT_NAME
                use_dash = is_derived

            tw = fitz.get_text_length(ann_text, fontname=font_n, fontsize=eff_fs)
            if test_assign:
                tw = max(tw, fitz.get_text_length(test_assign, fontname=font_n, fontsize=eff_fs))
            wc_text = ""
            if where_clause:
                # MSG v2.0 §3.1.2 pt.15: conditional clauses use "when".
                kw = getattr(ANNOTATION_STYLE, "conditional_keyword", "when")
                wc_text = f"{kw} {where_clause}"
                tw = max(tw, fitz.get_text_length(wc_text, fontname=_FONT_NAME, fontsize=eff_fs))
            if value_decode:
                vd_text = f"({value_decode})"
                tw = max(tw, fitz.get_text_length(vd_text, fontname=_FONT_NAME, fontsize=eff_fs))

            box_width = tw + 2 * _BOX_PADDING_X + _FT_SIDE_INSET

            # If this box would exceed page width, wrap to next line below
            if x_cursor + box_width > pw - 10.0 and x_cursor != base_x:
                # Fallback: can't fit side-by-side, skip (rare edge case)
                continue

            box_top = slot_y - eff_fs - _BOX_PADDING_Y
            box_rect = fitz.Rect(
                x_cursor,
                box_top,
                x_cursor + box_width,
                box_top + this_h,
            )

            # Test assignment is shown first (e.g. "VSTEST = Weight") followed
            # by the result variable, matching the AZ Findings annotation order.
            full_content = f"{test_assign}\n{ann_text}" if test_assign else ann_text
            if where_clause:
                full_content += f"\n{wc_text}"
            if value_decode:
                full_content += f"\n({value_decode})"

            _freetext(
                page, box_rect, full_content,
                fontsize=eff_fs, fontname=font_n,
                text_color=text_c, fill_color=fill_c, border_color=border_c,
                border_width=_BORDER_WIDTH, dashed=use_dash,
            )

            # Advance cursor to the RIGHT for next entry
            x_cursor += box_width + _MULTI_BOX_H_GAP
            any_drawn = True
            stats["total_annotations"] += 1

        # Mark the full occupied vertical range for this field
        if any_drawn:
            tracker.mark_occupied(page_idx, box_top_for_field, box_bottom_for_field)
            stats["pages_annotated"].add(page_idx)

    ref_page = doc[0]
    _append_legend_page(doc, ref_page.rect.width, ref_page.rect.height)

    toc = _build_toc(form_first_page, form_primary_domain, dict(form_visits))
    toc.append([1, "Colour Legend", doc.page_count])
    if toc:
        try:
            doc.set_toc(toc)
        except Exception as e:
            logger.warning(f"Could not set TOC: {e}")

    stats["pages_annotated"] = len(stats["pages_annotated"])
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_pdf_path), deflate=True, garbage=4)
    doc.close()

    logger.info(
        "PDF annotated: %d annotations on %d pages, %d multi-domain, "
        "%d duplicates skipped, %d not-submitted, %d skipped (no position)",
        stats["total_annotations"], stats["pages_annotated"],
        stats["multi_domain_fields"], stats["duplicates_skipped"],
        stats["not_submitted"], stats["skipped_no_position"],
    )

    return stats