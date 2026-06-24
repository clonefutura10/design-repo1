"""Shared pytest fixtures for the aCRF tool test-suite.

The end-to-end fixtures run the full pipeline once per CRF (session-scoped) so
the regression tests are fast despite operating on real multi-hundred-page PDFs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "input"

# Real CRFs used as golden inputs. Each represents a distinct layout family.
BLANK_CRF = INPUT_DIR / "blank_crf_clean.pdf"          # AZ-EDC numbered layout
NUMBERLESS_CRF = INPUT_DIR / "D9186R00001.pdf"         # position-based layout
DB_CRF = INPUT_DIR / "D5180C00007 - Annotated CRF V30 (1).pdf"  # DB spec tables


def _have(path: Path) -> bool:
    return path.exists()


def _run(path: Path):
    from app.services import run_pipeline
    return run_pipeline(path, path.name)


@pytest.fixture(scope="session")
def blank_job():
    if not _have(BLANK_CRF):
        pytest.skip(f"missing {BLANK_CRF}")
    return _run(BLANK_CRF)


@pytest.fixture(scope="session")
def numberless_job():
    if not _have(NUMBERLESS_CRF):
        pytest.skip(f"missing {NUMBERLESS_CRF}")
    return _run(NUMBERLESS_CRF)


@pytest.fixture(scope="session")
def db_job():
    if not _have(DB_CRF):
        pytest.skip(f"missing {DB_CRF}")
    return _run(DB_CRF)


@pytest.fixture(scope="session")
def blank_doc(blank_job):
    doc = fitz.open(str(blank_job.output_pdf_path))
    yield doc
    doc.close()
