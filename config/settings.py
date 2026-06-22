"""
Central configuration for the aCRF Automation System.

All paths, thresholds, model identifiers, and tuneable parameters.
Tuned for maximizing accuracy without LLM (Tiers 0-2 only).
"""

import os
from pathlib import Path
from dataclasses import dataclass, field

# Load .env file if present (python-dotenv optional — fails silently if absent)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Directory Structure
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "input"
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"
MODELS_DIR = PROJECT_ROOT / "models"

for _dir in (CACHE_DIR, OUTPUT_DIR, LOGS_DIR, MODELS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Input File Paths
# ─────────────────────────────────────────────────────────────────────────────

AZ_SPEC_FILE = INPUT_DIR / "AZ_RAW_to_SDTM_Specification_Template.xlsx"
AZ_CT_FILE = INPUT_DIR / "AZ_SDTM_CT.xlsx"
AZ_CORPORATE_FILE = INPUT_DIR / "AZ_Corporate_SDTM_Standards.xlsx"
AZ_MAP_RULE_FILE = INPUT_DIR / "AZ_Map_Rule_Spec.xlsx"
BLANK_CRF_FILE = INPUT_DIR / "blank_crf_clean.pdf"


# ─────────────────────────────────────────────────────────────────────────────
# Cache File Paths
# ─────────────────────────────────────────────────────────────────────────────

AZ_SPEC_LOOKUP_CACHE = CACHE_DIR / "az_spec_lookup.json"
AZ_SPEC_MODULE_INDEX_CACHE = CACHE_DIR / "az_spec_module_index.json"
CT_LOOKUP_CACHE = CACHE_DIR / "ct_lookup.json"
CORPORATE_VARIABLES_CACHE = CACHE_DIR / "corporate_variables.json"
CORPORATE_DATASETS_CACHE = CACHE_DIR / "corporate_datasets.json"
MAP_RULES_CACHE = CACHE_DIR / "map_rules.json"

AZ_SPEC_FAISS_INDEX = CACHE_DIR / "az_spec_index.faiss"
AZ_SPEC_FAISS_METADATA = CACHE_DIR / "az_spec_metadata.json"
CDISC_FAISS_INDEX = CACHE_DIR / "cdisc_index.faiss"
CDISC_FAISS_METADATA = CACHE_DIR / "cdisc_metadata.json"


# ─────────────────────────────────────────────────────────────────────────────
# Model Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ModelConfig:
    """Embedding, re-ranking, and LLM model configuration."""

    # Bi-encoder for FAISS
    embedding_model: str = "models/bge-small-en-v1.5"
    embedding_dimension: int = 384

    # Cross-encoder for Tier 2 re-ranking
    cross_encoder_model: str = "models/ms-marco-MiniLM-L-6-v2"
    cross_encoder_available: bool = True  # Set False if download fails

    # Device
    device: str = "cpu"
    embedding_batch_size: int = 64


# ─────────────────────────────────────────────────────────────────────────────
# LLM Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LLMConfig:
    """
    LLM endpoint configuration.

    Supports:
    - Ollama (local): base_url = "http://localhost:11434"
    - OpenAI-compatible: any endpoint with /v1/chat/completions
    - AZ internal HuggingFace: TBD endpoint
    - Google Colab via ngrok: temporary public URL
    """

    # Endpoint configuration — read from environment variables
    base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    model_name: str = os.getenv("LLM_MODEL_NAME", "Qwen3-0.6B")
    api_key: str = os.getenv("LLM_API_KEY", "")

    # Request parameters
    temperature: float = 0.3
    max_tokens: int = 10
    timeout_seconds: int = 60

    # Self-consistency voting
    num_votes: int = 3
    require_majority: bool = True

    # Retry configuration
    max_retries: int = 0
    retry_delay_seconds: float = 0.0

    # Master switch — set True when LLM endpoint is available
    enabled: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Resolution Thresholds (Tuned for No-LLM Maximum Accuracy)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ThresholdConfig:
    """
    Confidence thresholds — tuned for maximum accuracy without LLM.

    Without LLM, we need Tier 0 fuzzy and Tier 2 to resolve as much
    as possible while maintaining acceptable precision. Thresholds are
    lowered compared to LLM-heavy mode to accept more FAISS results.

    FAISS cosine similarity scores for this corpus typically range:
    - Same module, correct match: 0.82-0.96
    - Same module, wrong match: 0.70-0.82
    - Cross-module noise: 0.65-0.75
    """

    # Tier 0: Fuzzy match acceptance (within correct module)
    # Module-filtered search means higher precision — can lower threshold
    tier0_fuzzy_accept: float = 0.82
    tier0_fuzzy_gap: float = 0.04        # Small gap OK when module-filtered

    # Tier 2: Cross-encoder auto-acceptance (if available)
    tier2_faiss_only_accept: float = 0.72
    tier2_faiss_only_gap: float = 0.03

 

    # Tier 3: LLM voting confidence (for when LLM is enabled)
    tier3_unanimous_confidence: float = 0.97
    tier3_majority_confidence: float = 0.90

    # FAISS retrieval parameters
    faiss_top_k_spec: int = 20          # More candidates = better module filtering
    faiss_top_k_cdisc: int = 15
    cross_encoder_candidates: int = 10
    llm_candidates: int = 10


# ─────────────────────────────────────────────────────────────────────────────
# Excel Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExcelConfig:
    spec_main_sheet: str = "RAW-SDTM Mappings"
    spec_header_row: int = 2
    spec_data_start_row: int = 3
    spec_skip_sheets: tuple = (
        "Map Rule Specification", "Changes", "Change Requests",
        "TA Specific Datasets", "RELREC", "Change history for sep sheets",
    )
    spec_library_filter: tuple = ()
    corporate_datasets_sheet: str = "Datasets"
    corporate_variables_sheet: str = "Variables"
    corporate_codelists_sheet: str = "Codelists"
    ct_sheet: str = "AZ CDISC SDTM CT"
    map_rule_sheet: str = "Map Rule Specification"


# ─────────────────────────────────────────────────────────────────────────────
# Annotation Style — STRICT SDTM-MSG v2.0 (CDISC, 2021-03-30, latest version)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AnnotationStyleConfig:
    """
    Controls the appearance/format of annotations.

    Defaults implement the CDISC SDTM-MSG v2.0 conventions *strictly*
    (Section 3.1.2). The options remain configurable (not hardcoded per-CRF)
    so an alternative house style can be selected, but out of the box every
    output is MSG-compliant.

    MSG v2.0 reference for each option is given inline.
    """

    # MSG §3.1.2 pt.5: variable annotations are standalone capitalised names
    # (``BRTHDTC``), never dotted ``DOMAIN.VARIABLE``.
    use_domain_prefix: bool = False

    # MSG §3.1.2 pt.5: dataset labels use Title-Case inside the header, e.g.
    # ``DM (Demographics)``.
    title_case_headers: bool = True

    # MSG §3.1.2 pt.14: explicit values are NOT quoted
    # (``DSCAT = PROTOCOL MILESTONE``).
    quote_where_values: bool = False

    # MSG findings examples annotate via the TESTCD when-clause only; the
    # ``--TEST = <Name>`` companion is an AZ extension and is OFF for strict MSG.
    emit_test_assignment: bool = False

    # Render annotation boxes onto the page content stream (instead of as
    # FreeText annotations) so the colours render identically in browser PDF
    # viewers (pdf.js / pdfium), not just Adobe Acrobat. MSG pt.13 only requires
    # that flattened text remain searchable, which content rendering preserves.
    render_as_content: bool = True

    # MSG §3.1.2 pt.5 (and the v1.0→v2.0 rationale on p.9): domain headers use
    # the ``DM (Demographics)`` parenthesis form, NOT the v1.0 ``DM = ...`` form.
    # "paren" => MSG v2.0 ; "equals" => legacy v1.0 / AZ house style.
    domain_header_format: str = "paren"

    # MSG §3.1.2 pt.15: conditional (when/then) annotations use the keyword
    # ``when`` — e.g. ``VSORRES when VSTESTCD = TEMP``.
    # "when" => MSG v2.0 ; "where" => AZ house style.
    conditional_keyword: str = "when"

    # MSG §3.1.2 pt.1c/pt.5: supplemental qualifiers are annotated in
    # equivalence to the parent domain as ``<QNAM> in SUPP<DOMAIN>``
    # (e.g. ``AEACN01 in SUPPAE``); the SUPP dataset name itself is not annotated.
    # "in" => MSG v2.0 ; "qval" => AZ ``SUPPxx.QVAL where QNAM = <var>`` style.
    supp_format: str = "in"


# ─────────────────────────────────────────────────────────────────────────────
# Singletons
# ─────────────────────────────────────────────────────────────────────────────

ANNOTATION_STYLE = AnnotationStyleConfig()
MODELS = ModelConfig()
LLM = LLMConfig()
THRESHOLDS = ThresholdConfig()
EXCEL = ExcelConfig()