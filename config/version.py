"""
Tool version & provenance.

Used to stamp every output (annotated PDF metadata + mapping CSV) so an aCRF can
be reproduced and audited: which tool version, rule-set, and CT/standard the
annotations were generated from.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

# Tool version. Bump on any change that can alter annotation output.
TOOL_VERSION = "1.0.0"

# CDISC standard the annotation conventions follow.
MSG_VERSION = "SDTM-MSG v2.0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _file_fingerprint(path: Path) -> str:
    """Short content hash of a file, or '' if absent."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception:
        return ""


def _json_version(path: Path) -> str:
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("version", ""))
    except Exception:
        return ""


def provenance() -> dict[str, str]:
    """Return a provenance record describing how an output was produced."""
    rules_dir = PROJECT_ROOT / "config" / "rules"
    cache_dir = PROJECT_ROOT / "cache"
    return {
        "tool_version": TOOL_VERSION,
        "msg_version": MSG_VERSION,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "form_rules_fp": _file_fingerprint(rules_dir / "form_rules.json"),
        "universal_rules_fp": _file_fingerprint(rules_dir / "universal_rules.json"),
        "learned_mappings_version": _json_version(cache_dir / "learned_mappings.json"),
    }
