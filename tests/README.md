# Test suite

```bash
pip install pytest
python -m pytest                 # full suite (unit + end-to-end regression)
python -m pytest tests/test_noise_filter.py   # fast unit subset
```

## Layout

| File | Scope | Speed |
|---|---|---|
| `test_noise_filter.py` | EDC-scaffolding / noise detection | fast |
| `test_findings_qualifier.py` | Findings TESTCD + MSG where-clause style | fast |
| `test_annotation_format.py` | MSG v2.0 colours, headers, SUPP/when format, TOC | fast |
| `test_extractor.py` | parser routing, EDC spec-table detection | fast |
| `test_regression.py` | end-to-end golden invariants on the real CRFs | ~30s |

The end-to-end tests run the full pipeline on the real input CRFs and assert
stable invariants (resolution-rate floors, EDC spec pages un-annotated, editable
FreeText, MSG fill colours present, bookmark structure). They `skip` if an input
PDF is absent.

## Accuracy harness

`scripts/accuracy_report.py` scores the resolver against the curated ground
truth in `cache/learned_mappings.json`:

```bash
python scripts/accuracy_report.py                 # generalisation (learned OFF)
python scripts/accuracy_report.py --with-learned  # reproduction (learned ON)
```

- **Reproduction** (learned ON) shows how well known mappings are reproduced.
- **Generalisation** (learned OFF) disables the memorised table to show what the
  rule/standard/spec engine derives on its own — a stable regression metric and
  an honest measure of cross-study robustness.
