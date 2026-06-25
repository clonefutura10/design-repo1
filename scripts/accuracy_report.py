"""
Accuracy / generalisation harness for the SDTM resolver.

Scores how well the deterministic rule + standards + spec engine reproduces the
curated ground-truth mappings in cache/learned_mappings.json (which were
extracted from human-annotated reference aCRFs).

The learned table is DISABLED during scoring, so this measures genuine
GENERALISATION — what the engine gets right without memorising the answer —
rather than reproduction. This makes it a stable regression metric: re-run it
after any rule/standard change to see whether accuracy moved.

Usage:
    python scripts/accuracy_report.py
    python scripts/accuracy_report.py --limit 2000
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import CACHE_DIR
import src.resolution.tier0_rules as tier0_mod
from src.resolution.tier0_rules import Tier0Rules, set_study_context
from src.resolution.tier1_not_submitted import Tier1NotSubmitted


def _norm_dom(d: str) -> str:
    d = (d or "").upper()
    return d[4:] if d.startswith("SUPP") else d


def load_truth(limit: int | None) -> list[tuple[str, str, dict]]:
    """Return (form_or_domain_prefix, label, truth_mapping) triples."""
    data = json.loads((CACHE_DIR / "learned_mappings.json").read_text(encoding="utf-8"))
    triples: list[tuple[str, str, dict]] = []
    for key, val in data.get("mappings", {}).items():
        prefix, _, label = key.partition("|")
        if not prefix or not label:          # skip bare "|label" duplicates
            continue
        if not (val.get("variable") or val.get("is_not_submitted")):
            continue
        triples.append((prefix, label, val))
        if limit and len(triples) >= limit:
            break
    return triples


def score(limit: int | None, keep_learned: bool) -> None:
    if not keep_learned:
        tier0_mod._LEARNED_MAPPINGS = {}      # disable memorisation
    truth = load_truth(limit)
    set_study_context({p for p, _, _ in truth})
    tier0, tier1 = Tier0Rules(), Tier1NotSubmitted()

    n = exact = dom_ok = var_ok = covered = 0
    tiers: Counter = Counter()
    misses: list[str] = []

    for prefix, label, t in truth:
        n += 1
        r = tier1.resolve(field_label=label, form_code=prefix) or \
            tier0.resolve(form_code=prefix, field_label=label, form_name="")
        t_dom, t_var, t_ns = _norm_dom(t.get("domain")), (t.get("variable") or "").upper(), t.get("is_not_submitted")
        if r is None:
            if len(misses) < 40:
                misses.append(f"[unresolved] {label[:42]:42} -> {t_dom}.{t_var}")
            continue
        covered += 1
        tiers[r.tier.value] += 1
        p_dom, p_var, p_ns = _norm_dom(r.sdtm_domain), (r.sdtm_variable or "").upper(), r.is_not_submitted
        if t_ns and p_ns:
            exact += 1; dom_ok += 1; var_ok += 1
            continue
        if t_dom and p_dom == t_dom:
            dom_ok += 1
        if t_var and p_var == t_var:
            var_ok += 1
        if t_dom and t_var and p_dom == t_dom and p_var == t_var:
            exact += 1
        elif len(misses) < 40:
            misses.append(f"{label[:40]:40} true={t_dom}.{t_var:9} pred={p_dom}.{p_var}")

    def pct(x):
        return f"{100.0 * x / n:.1f}%" if n else "n/a"

    mode = "learned ENABLED (reproduction)" if keep_learned else "learned DISABLED (generalisation)"
    print("=" * 60)
    print(f"  RESOLVER ACCURACY — {mode}")
    print("=" * 60)
    print(f"  Ground-truth fields : {n}")
    print(f"  Coverage            : {pct(covered)}")
    print(f"  Exact (dom+var)     : {pct(exact)}")
    print(f"  Domain correct      : {pct(dom_ok)}")
    print(f"  Variable correct    : {pct(var_ok)}")
    print(f"  Tiers used          : {dict(tiers)}")
    print("=" * 60)
    print("  Sample mismatches:")
    for s in misses[:25]:
        print("   ", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--with-learned", action="store_true",
                    help="keep the learned table on (measures reproduction, not generalisation)")
    args = ap.parse_args()
    score(args.limit, args.with_learned)


if __name__ == "__main__":
    main()
