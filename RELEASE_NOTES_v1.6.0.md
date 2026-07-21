# Universal File to Markdown v1.6.0

Universal File to Markdown v1.6.0 turns the project into a schema-validated, offline-first document normalization skill for AI analysis, RAG, auditing, and downstream automation.

## Highlights

- Converts PDF, scanned images, DOCX, XLSX/XLSM, PPTX, CSV/TSV, JSON, EML, and Pandoc-supported markup.
- Produces `document.md`, hierarchical `document.json`, bounded `chunks.jsonl`, canonical table assets, extracted assets, manifest, and quality report.
- Uses canonical schema version 1.0 independently of skill version 1.6.0.
- Enforces a 2,000-character chunk hard limit with table-header repetition.
- Preserves Office merged cells in merge-aware HTML exports.
- Supports Big5/CP950-aware encoding scoring.
- Routes digital and scanned PDF pages independently.
- Adds shape-level PPTX, block-level XLSX, and located PDF elements.
- Adds bundle validation for schemas, hierarchy, references, counts, chunk limits, table bounds, and assets.
- Adds runtime capability preflight and GitHub Actions validation.

## Correctness and safety fixes

- Corrupt OOXML is no longer misreported as password protected.
- Ordinary PPTX text boxes are no longer converted into false bullet lists.
- Image OCR provenance reports the actual RapidOCR or Tesseract engine.
- Failed reruns remove stale canonical artifacts.
- SmartArt and embedded OLE content are detected and reported instead of silently dropped.

## Installation and verification

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/capability_probe.py --json
python -m pytest tests/ -q
```

## Usage

```bash
python scripts/router.py INPUT_FILE --output OUTPUT_DIRECTORY
python scripts/validate_bundle.py OUTPUT_DIRECTORY
```

Always inspect `conversion-report.json`. A successful conversion should also report `bundle_validation.status = passed`.

## Known limitations

- Complex scanned tables remain heuristic and may require a heavier parser.
- SmartArt and embedded OLE objects are detected but not expanded.
- Excel chart objects are represented as references rather than fully rendered series.
- PPTX reading order is based on geometry and may be imperfect for overlapping layouts.
- DOCX tracked changes, nested tables, and exact inline-image anchoring remain limited.
- Legacy `.doc`, `.xls`, and `.ppt` files must first be converted to OOXML.

## License

This release is licensed under the Apache License 2.0.

See `CHANGELOG.md` for the full version history.