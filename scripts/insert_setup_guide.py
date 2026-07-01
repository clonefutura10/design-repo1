"""
Replaces the "Getting Started" setup section in docs/aCRF_Annotation_Engine_User_Guide.docx
with a compressed, no-hand-holding version: commands and steps only, no
glossary, no "what is a terminal" explanations, no reassurance asides.

Removes any existing section between the "Getting Started ..." heading and
the next Heading 1 (the start of the pre-existing guide content), then
inserts the new version in its place. Safe to re-run.
"""
from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.oxml.ns import qn

_HERE = Path(__file__).resolve().parent.parent
TARGET = _HERE / "docs" / "aCRF_Annotation_Engine_User_Guide.docx"

AZ_PURPLE = RGBColor(0x6B, 0x2D, 0x88)
AZ_MAGENTA = RGBColor(0x83, 0x00, 0x51)
GREY = RGBColor(0x6B, 0x6B, 0x6B)
DARK = RGBColor(0x1A, 0x1A, 0x1A)

PROJECT_PATH = r"C:\Users\kjvd631\OneDrive - AZCollaboration\Desktop\acrf_tool"
SECTION_HEADING = "Getting Started — Installing & Running the Tool on Your Computer"


def _build_scratch_doc() -> Document:
    doc = Document()

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = DARK

    for lvl, sz, col in [("Heading 1", 15, AZ_MAGENTA), ("Heading 2", 12, AZ_PURPLE)]:
        st = doc.styles[lvl]
        st.font.name = "Calibri"
        st.font.size = Pt(sz)
        st.font.color.rgb = col
        st.font.bold = True

    def numbered(text):
        p = doc.add_paragraph(style="List Number")
        p.paragraph_format.space_after = Pt(3)
        p.add_run(text)
        return p

    def cmd(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.left_indent = Inches(0.2)
        r = p.add_run(text)
        r.font.name = "Consolas"; r.font.size = Pt(10); r.font.color.rgb = AZ_PURPLE; r.bold = True
        return p

    def body(text, space=6):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(space)
        p.add_run(text)
        return p

    def table(headers, rows, widths=None):
        from docx.enum.table import WD_TABLE_ALIGNMENT
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Light Grid Accent 1"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for c, txt in zip(t.rows[0].cells, headers):
            c.paragraphs[0].add_run(txt).bold = True
        for row in rows:
            cells = t.add_row().cells
            for i, val in enumerate(row):
                run = cells[i].paragraphs[0].add_run(val)
                if i == 0:
                    run.bold = True
        if widths:
            for r in t.rows:
                for i, w in enumerate(widths):
                    r.cells[i].width = Inches(w)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    # ==================== CONTENT ====================
    doc.add_heading(SECTION_HEADING, level=1)
    body("One-time setup, about 15 minutes. Project folder:", 2)
    p = doc.add_paragraph(); p.paragraph_format.left_indent = Inches(0.2)
    r = p.add_run(PROJECT_PATH)
    r.font.name = "Consolas"; r.font.size = Pt(9.5); r.font.color.rgb = AZ_PURPLE; r.bold = True
    p.paragraph_format.space_after = Pt(10)

    doc.add_heading("1. Get the folder", level=2)
    numbered("Get the acrf_tool folder shared to your OneDrive at the path above. "
              "Wait for it to fully sync (green tick in File Explorer).")

    doc.add_heading("2. Install prerequisites (AZ Software Store)", level=2)
    numbered("Install: Visual Studio Code, Python 3.11, Node.js (LTS). Search "
              "each by name in the AZ Software Store / Company Portal. "
              "Not available there → raise an IT ticket for the three by name.")

    doc.add_heading("3. Open the project", level=2)
    numbered("Open VS Code → File → Open Folder → select acrf_tool.")
    numbered("Terminal → New Terminal.")

    doc.add_heading("4. Backend (Terminal 1)", level=2)
    cmd("python -m venv venv")
    cmd(".\\venv\\Scripts\\Activate.ps1")
    body("(Command Prompt instead of PowerShell: venv\\Scripts\\activate.bat)", 6)
    cmd("pip install -r requirements.txt")
    cmd("python -m uvicorn app.main:app --reload --port 8000")
    body("Leave this running.", 8)

    doc.add_heading("5. Frontend (Terminal 2 — click “+”)", level=2)
    cmd("cd frontend")
    cmd("npm install")
    cmd("npm run dev")

    doc.add_heading("6. Open it", level=2)
    numbered("Browser → http://localhost:5173")

    doc.add_heading("Next time (no reinstall needed)", level=2)
    cmd("Terminal 1:  .\\venv\\Scripts\\Activate.ps1   →   python -m uvicorn app.main:app --reload --port 8000")
    cmd("Terminal 2:  cd frontend   →   npm run dev")
    body("Then open http://localhost:5173", 8)

    doc.add_heading("Troubleshooting", level=2)
    table(
        ["Issue", "Fix"],
        [
            ("“python”/“npm” not recognized", "Reinstall with “Add to PATH” "
             "checked; restart VS Code."),
            ("Execution policy error on activate",
             "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"),
            ("Port 8000 / 5173 already in use", "Close old terminals / "
             "restart the machine."),
            ("Nothing at localhost:5173", "Confirm both terminals (backend + "
             "frontend) are still running with no errors."),
            ("Folder looks incomplete", "OneDrive still syncing — wait for "
             "the green tick."),
        ],
        widths=[2.3, 3.9],
    )

    doc.add_page_break()
    return doc


def main():
    target = Document(TARGET)
    body_el = target.element.body

    # Locate the start heading and the next Heading 1 (the true end boundary)
    # by walking body children directly, so tables in between are included.
    start_el = None
    end_el = None
    for child in body_el:
        if child.tag != qn("w:p"):
            continue
        from docx.text.paragraph import Paragraph
        para = Paragraph(child, target)
        if start_el is None:
            if para.style.name == "Heading 1" and para.text.strip() == SECTION_HEADING:
                start_el = child
            continue
        if end_el is None and para.style.name == "Heading 1":
            end_el = child
            break

    if start_el is None:
        raise SystemExit(f"Section heading {SECTION_HEADING!r} not found — nothing to replace.")
    if end_el is None:
        raise SystemExit("Could not find the next Heading 1 after the setup section — refusing to guess.")

    # Remove every element (paragraphs and tables) from start_el (inclusive)
    # up to but not including end_el.
    to_remove = []
    el = start_el
    while el is not None and el is not end_el:
        to_remove.append(el)
        el = el.getnext()
    for el in to_remove:
        body_el.remove(el)

    # Insert the compressed replacement immediately before end_el.
    scratch = _build_scratch_doc()
    scratch_body = scratch.element.body
    scratch_children = [c for c in scratch_body if c.tag != qn("w:sectPr")]
    for c in scratch_children:
        end_el.addprevious(deepcopy(c))

    target.save(TARGET)
    print("Replaced Getting Started section with compressed version in:", TARGET)


if __name__ == "__main__":
    main()
