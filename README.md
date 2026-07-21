# Universal File to Markdown

[繁體中文](README.zh-TW.md) · [Changelog](CHANGELOG.md)

A deterministic, offline-first document normalization skill that converts supported files into Markdown and a schema-validated bundle for AI analysis, RAG, auditing, and downstream automation.

The project is designed for environments where conversion must remain transparent and traceable. It does not treat `document.md` alone as proof of success: every run also produces a quality report, source manifest, canonical elements, bounded chunks, table assets, and validation results.

## Documentation

- [English README](README.md)
- [繁體中文 README](README.zh-TW.md)
- [English changelog](CHANGELOG.md)
- [繁體中文變更紀錄](CHANGELOG.zh-TW.md)
- [AI skill operating contract](SKILL.md)
- [Format capability matrix](references/capability_matrix.md)
- [Engine notes and escalation guidance](references/engine_notes.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Support policy](SUPPORT.md)
- [Governance](GOVERNANCE.md)
- [Release process](RELEASING.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Licensing guide](docs/LICENSING.md)

## Highlights

- Converts PDF, scanned images, DOCX, XLSX/XLSM, PPTX, CSV/TSV, JSON, EML, and Pandoc-supported markup.
- Uses lightweight structural parsers and offline OCR; no PyTorch runtime or external model download is required.
- Handles Traditional Chinese Big5/CP950 encoding candidates explicitly.
- Preserves merged Office tables with rowspan/colspan-aware HTML output.
- Routes mixed digital/scanned PDF pages independently.
- Produces canonical hierarchical elements with page, sheet, slide, shape, table, and bounding-box locators where available.
- Emits RAG chunks with a hard maximum of 2,000 characters.
- Detects unsupported or uncertain content instead of silently reporting success.
- Validates schemas, hierarchy, chunk references, table dimensions, assets, and bundle consistency.

## Supported formats

| Input | Primary engine | Canonical granularity | Notes |
|---|---|---|---|
| DOCX | python-docx + OOXML | heading, paragraph, list item, table | Formatting, links, notes, headers/footers, merged cells |
| XLSX/XLSM | openpyxl | sheet, blank-separated block, table, chart/image reference | Formulas, comments, merged cells, hidden-state metadata |
| PPTX | python-pptx + OOXML | slide, group, title, paragraph, list, table, chart, image, note | Bullet inheritance, stable assets, SmartArt/OLE disclosure |
| Digital PDF | PyMuPDF + pdfplumber | page, located text block, table | Table-text de-duplication and bounding boxes |
| Scanned PDF | RapidOCR; Tesseract fallback | page, OCR region, table | OCR confidence and table-likelihood reporting |
| PNG/JPEG/TIFF/BMP/WebP | RapidOCR; Tesseract fallback | OCR region, table | Direct offline image OCR |
| CSV/TSV | Python stdlib CSV | canonical table | Encoding scoring with Traditional Chinese support |
| JSON | Python stdlib JSON | structured block | Pretty-printed Unicode JSON |
| EML | Python stdlib email | email, attachment | Sanitized collision-safe attachment names |
| HTML/EPUB/RST/Org/TeX | Pandoc | structured block | Explicit failure when Pandoc is unavailable |

Legacy `.doc`, `.xls`, and `.ppt` files are not parsed directly. Convert them to OOXML first.

## Output bundle

Each conversion writes an output directory containing:

```text
document.md              Human- and LLM-readable Markdown
document.json            Canonical hierarchical elements, schema 1.0
chunks.jsonl              Locator-rich RAG chunks, max 2,000 characters
tables/                   Canonical JSON plus CSV and merge-aware HTML
assets/                   Extracted images and attachments
manifest.json             Source SHA-256, versions, timestamp, final status
conversion-report.json   Engine details, warnings, and bundle validation
```

A failed rerun clears known generated artifacts first, preventing stale canonical outputs from surviving a later failure.

## Installation

Python 3.10 or later is recommended.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Optional system tools:

- `tesseract`: Latin-script OCR fallback.
- `pandoc`: HTML, EPUB, RST, Org, and TeX conversion paths.

Check the runtime before conversion:

```bash
python scripts/capability_probe.py --json
```

The probe exits non-zero when a required Python dependency is missing. Optional system tools are reported without failing the probe.

## Usage

```bash
python scripts/router.py INPUT_FILE --output OUTPUT_DIRECTORY
```

For ambiguous legacy encodings, provide an explicit codec:

```bash
python scripts/router.py input.csv --output output --encoding gb18030
```

Validate an existing bundle independently:

```bash
python scripts/validate_bundle.py OUTPUT_DIRECTORY
```

The router exits non-zero when the final conversion status is `failed`.

## Reading the result

Always inspect `conversion-report.json`.

- `passed`: conversion and bundle validation succeeded without detected loss.
- `passed_with_warnings`: output is usable, but one or more uncertainties or unsupported structures were disclosed.
- `failed`: canonical and RAG outputs must not be treated as valid.

A successful bundle should also contain:

```json
{
  "bundle_validation": {
    "status": "passed"
  }
}
```

Typical warnings include unavailable formula results, ambiguous encoding, low OCR confidence, likely but unreconstructed scanned tables, SmartArt/OLE content not extracted, and Excel charts represented only as references.

## Canonical contracts

Skill and schema versions are independent:

```text
skill_version: 1.6.0
document/table/chunk schema_version: 1.0
```

Every canonical element has fixed fields for hierarchy, content format, engine, confidence, source locator, properties, and warnings. Canonical tables preserve merge anchors in `cells` and provide a rectangular `grid` for CSV and downstream processing.

JSON Schemas are stored in `schemas/`. Format-specific granularity is documented in `references/capability_matrix.md`.

## Known boundaries

- Scanned table reconstruction is geometric and heuristic; complex borderless or merged tables may require a heavier parser.
- SmartArt and embedded OLE objects are detected and located but not expanded.
- Excel chart objects are represented as references; plotted series are not rendered in this release.
- PPTX reading order uses top/left geometry and may be wrong for overlapping or multi-flow layouts.
- DOCX tracked changes, nested tables, and exact inline-image anchoring remain limited.
- Legacy binary Office files and round-trip conversion back to Office formats are out of scope.

## Development and release checks

```bash
python scripts/capability_probe.py --json
python -m pytest tests/ -q
python -m py_compile scripts/*.py tests/*.py
```

GitHub Actions runs these checks on pushes and pull requests. Release-specific checks are documented in `RELEASING.md` and `RELEASE_CHECKLIST.md`.

## Project structure

```text
SKILL.md                    AI skill operating contract
scripts/                    Router, converters, models, validation, utilities
schemas/                    Canonical JSON Schemas
references/                 Capability matrix and engine notes
tests/                      Regression and integration tests
requirements.txt            Runtime and test dependencies
```

## License

Licensed under the [Apache License 2.0](LICENSE).

The license permits commercial use, modification, and redistribution subject to its terms, and includes an express contributor patent grant. Third-party dependencies retain their own licenses; see `THIRD_PARTY_NOTICES.md` and `LICENSES.md`.