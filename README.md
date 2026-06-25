# aCRF Annotation Engine

Automated SDTM annotation tool for AstraZeneca blank CRF PDFs.  
Uploads a blank CRF PDF → resolves every field to its SDTM variable → writes a fully annotated aCRF PDF.

---

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Add input files
Place the following proprietary files in `input/` (gitignored):
- `AZ_RAW_to_SDTM_Specification_Template.xlsx`
- `AZ_SDTM_CT.xlsx`
- `AZ_Corporate_SDTM_Standards.xlsx`
- `AZ_Map_Rule_Spec.xlsx`
- `blank_crf_clean.pdf`

### 3. Build the cache
```bash
python scripts/build_cache.py
```

### 4. Configure environment (optional)
```bash
cp .env.example .env
# Edit .env to set LLM endpoint if needed
```

### 5. Start the backend
```bash
python -m uvicorn app.main:app --reload --port 8000
```

### 6. Start the frontend
```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## Architecture

```
blank_crf.pdf
     │
     ▼
┌─────────────────────┐
│  PDF Parsing Engine  │  PyMuPDF · form headers · field extraction · noise filter
└─────────────────────┘
     │
     ▼
┌──────────────────────────┐
│  Multi-tier Resolution   │
│  Tier 1 → NOT SUBMITTED  │  Gating triggers, non-collected fields
│  Tier 0-A → Regex Rules  │  Hardcoded per-form rules (confidence 0.98)
│  Tier 0-B → SDTM Std     │  CDISC formal labels (confidence 0.92)
│  Tier 0-C → AZ Spec      │  CRF-facing labels (confidence 0.90)
└──────────────────────────┘
     │
     ▼
┌──────────────────────────┐
│  PDF Annotation Writer   │  Domain colour-coding · bookmarks · overlap avoidance
└──────────────────────────┘
     │
     ▼
  aCRF_annotated.pdf
```

---

## Testing & Accuracy

### Running the test suite
```bash
python -m pytest          # 77 tests, ~40s
```

The suite locks down the annotation rules so a future change can't silently
break SDTM-MSG v2.0 compliance. Each file guards a specific behaviour:

| Test file | What it verifies | Why it matters |
|---|---|---|
| `test_noise_filter.py` | EDC scaffolding (SAS var defs, codelist defs, length specs) is dropped | Keeps machine plumbing out of the aCRF |
| `test_findings_qualifier.py` | `--TESTCD` assignment and **unquoted** `when` where-clauses | MSG findings convention |
| `test_annotation_format.py` | 4-colour page sequence, `DM (Demographics)` headers, `X in SUPPxx`, TOC hierarchy | MSG §3.1.2 visual rules |
| `test_extractor.py` | Parser routing — numbered vs. position vs. spec-table CRFs; spec pages skipped when real screens exist | Robust DB/Raw CRF support |
| `test_mapping_export.py` | 16-column traceability CSV + `review_flag` | Audit / reviewer handoff |
| `test_provenance.py` | Tool/MSG version + rule fingerprints stamped into PDF metadata; write failures surfaced | Reproducibility |
| `test_derived_and_meddra.py` | AGE/AGEU/`--DECOD` flagged derived (dashed border); MedDRA/WHO-Drug fields re-annotated as coded variables | MSG derived-variable convention |
| `test_regression.py` | End-to-end golden invariants | Catches cross-cutting regressions |

### Accuracy harness
```bash
python scripts/accuracy_report.py                  # generalisation (learned table OFF)
python scripts/accuracy_report.py --with-learned   # reproduction (learned table ON)
```

Scores the deterministic resolver against curated ground truth in
`cache/learned_mappings.json` (extracted from human-annotated reference aCRFs).

| Mode | Exact (domain+variable) | What it means |
|---|---|---|
| Reproduction (`--with-learned`) | **96.0%** | Operational accuracy on previously-seen studies — what the tool produces in practice |
| Generalisation (default) | **8.2%** | Pure rule/standard/spec coverage on *unseen* labels, with memorised answers disabled |

Measured over **5,073** ground-truth fields. The large gap is expected and
honest: the tool's day-to-day accuracy leans on the learned table built from
reference aCRFs. The generalisation number is the stable regression metric —
re-run it after any rule change to see whether the deterministic engine moved.

### Where these are useful
- **CI gate** — run `pytest` on every PR so annotation-rule regressions fail the build.
- **Pre-submission QA** — the mapping CSV's `review_flag` (`UNRESOLVED` / `LOW_CONFIDENCE`, confidence < 0.90) gives reviewers a worklist instead of eyeballing the whole PDF.
- **Regression after onboarding a new study** — add its mappings, re-run the accuracy harness, and confirm the generalisation number didn't drop.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/annotate` | Upload blank CRF PDF → run pipeline |
| `GET` | `/api/v1/annotate/{id}/download` | Download annotated PDF |
| `GET` | `/api/v1/annotate/{id}/stats` | Job statistics |
| `GET` | `/api/v1/annotate/{id}/details` | Full field mapping table |
| `GET` | `/api/v1/annotate/{id}/mapping.csv` | 16-column traceability CSV (with review flags) |
| `GET` | `/api/v1/jobs` | List all jobs |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

---

## Project Structure

```
├── app/                  FastAPI application
│   ├── main.py
│   ├── routers/
│   ├── schemas.py
│   └── services.py
├── src/                  Core pipeline
│   ├── pdf_parser/       PDF extraction
│   ├── resolution/       Tier 0/1 resolvers
│   ├── annotator/        PDF writer
│   └── utils/
├── config/               Settings & tokens
├── scripts/              build_cache.py
├── cache/                Generated JSON registries
├── input/                Input files (gitignored)
├── frontend/             React + TypeScript SPA
└── requirements.txt
```

---

## Environment Variables

See `.env.example`. All variables are optional for Tier 0/1 operation.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_BASE_URL` | `http://localhost:11434` | LLM endpoint (Ollama/OpenAI-compat) |
| `LLM_MODEL_NAME` | `Qwen3-0.6B` | Model identifier |
| `LLM_API_KEY` | _(empty)_ | API key if required |

