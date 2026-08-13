# Universal File to Markdown v1.8.1

## Highlights

- Adds deterministic, shared PDF/PPTX reading-order metadata and
  strong-evidence structural associations without changing schema 1.0.
- Preserves parser-derived PDF `source_extraction_index` separately from the
  deterministic visual reading order for auditability.
- Adds the optional, validated chunk consumer contract and bounded
  `embedding_text` projection while preserving source-derived `text`.
- Restores PR and `main` validation workflows, canonical release-package
  construction, and aligned AI Review advisory decisions.

## Compatibility and boundaries

Document, table, and chunk schema versions remain `1.0`. New layout,
association, and consumer-context fields are optional. Deterministic layout
rules provide reproducible geometry-based output; they do not claim to know
author intent. Retrieval relevance still needs downstream queries and
ground-truth evaluation.

## Validation

Run `python scripts/capability_probe.py --json`, `python -m pytest tests/ -q`,
and `python scripts/check_release_consistency.py` in a supported Python 3.10–3.12
environment. See [CHANGELOG.md](CHANGELOG.md) for the full change history.
