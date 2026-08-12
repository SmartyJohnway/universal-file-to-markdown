# Universal File to Markdown

[繁體中文](README.zh-TW.md) · [Changelog](CHANGELOG.md)

Evidence-first, fidelity-oriented document extraction skill for AI agents. It extracts supported files into Markdown and a schema-validated bundle while prioritizing source correctness, content completeness, traceability, and AI handoff.

The project is designed for environments where conversion must remain transparent and traceable. It does not treat `document.md` alone as proof of success: every run also produces a quality report, source manifest, canonical elements, bounded chunks, table assets, and validation results.

## Documentation

- [English README](README.md)
- [繁體中文 README](README.zh-TW.md)
- [English changelog](CHANGELOG.md)
- [繁體中文變更紀錄](CHANGELOG.zh-TW.md)
- [AI skill operating contract](SKILL.md)
- [Versioning](VERSIONING.md)
- [Format capability matrix](references/capability_matrix.md)
- [Engine notes and escalation guidance](references/engine_notes.md)
- [Chunk consumer contract](references/chunk_consumer_contract.md)
- [Optional Tier-2 adapter contract](references/tier2_adapter_contract.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Support policy](SUPPORT.md)
- [Governance](GOVERNANCE.md)
- [Release process](RELEASING.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Licensing guide](docs/LICENSING.md)

## Highlights

- Converts PDF, scanned images, DOCX, XLSX/XLSM, PPTX, CSV/TSV, JSON, EML, and Pandoc-supported markup.
- Uses lightweight structural parsers and offline OCR by default; no PyTorch runtime or external model download is required for the core route.
- Offers an opt-in, isolated, offline-manifested Tier-2 candidate adapter without replacing native canonical evidence.
- Handles Traditional Chinese Big5/CP950 encoding candidates explicitly.
- Preserves merged Office tables with rowspan/colspan-aware HTML output.
- Routes mixed digital/scanned PDF pages independently.
- Produces canonical hierarchical elements with page, sheet, slide, shape, table, and bounding-box locators where available.
- Applies deterministic column/role-aware PDF and PPTX reading plans and records additive layout hints on canonical elements.
- Links captions and speaker notes only when prefix, geometry, or OOXML relationships provide strong evidence.
- Emits RAG chunks plus a validated ID-only consumer context projection; both source and embedding views have a hard maximum of 2,000 characters.
- Detects unsupported or uncertain content instead of silently reporting success.
- Validates schemas, hierarchy, chunk references, table dimensions, assets, and bundle consistency.

## Supported formats

| Input | Primary engine | Canonical granularity | Notes |
|---|---|---|---|
| DOCX | python-docx + OOXML | heading, paragraph, list item, table | Formatting, links, notes, headers/footers, merged cells |
| XLSX/XLSM | openpyxl | sheet, blank-separated block, table, chart/image reference | Formulas, comments, merged cells, hidden-state metadata |
| PPTX | python-pptx + OOXML | slide, group, title, paragraph, list, table, chart, image, note | Role/column reading plan, bullet inheritance, SmartArt/OLE disclosure |
| Digital PDF | PyMuPDF + pdfplumber | page, located text block, table | Line-aware XY-cut order, bbox table insertion, de-duplication |
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
tier2/                   Optional candidate sidecar; absent by default
```

A failed rerun clears known generated artifacts first, preventing stale canonical outputs from surviving a later failure.

## Installation

Supported Python: 3.10–3.12. Primary qualified runtime: Python 3.11. Python 3.13 is not currently supported.

Declared RapidOCR requirement: `rapidocr-onnxruntime>=1.4,<2`. Qualified version: `1.4.4`.

**Linux:** `libGL.so.1` may be required for OpenCV/RapidOCR. Tesseract is required when using the `pytesseract` fallback.

**Windows:** the Microsoft Visual C++ runtime may be required for OpenCV. The Tesseract executable must be installed and discoverable when the fallback is used.

Pandoc is an optional dependency: it is not required for the core profile and is required only for optional Pandoc-enabled routes.

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

Score downstream chunk context across one or more bundles:

```bash
python scripts/score_chunk_context.py OUTPUT_DIRECTORY [OUTPUT_DIRECTORY ...]
```

Optional Tier-2 is disabled by default. In a separately installed and
qualified Docling environment, generate a candidate only for allowlisted
quality signals:

```bash
python scripts/router.py source.pdf --output bundle \
  --tier2 auto \
  --tier2-model-manifest /models/docling/tier2-model-manifest.json
```

The candidate never replaces `document.json`, chunks, or tables. See the
[Tier-2 adapter contract](references/tier2_adapter_contract.md).

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

Current development target: `1.9.0`
Latest published stable release: `1.7.2`

`v1.7.1` was an unpublished integration milestone superseded by `v1.7.2`.

`VERSION` is the canonical current skill-version source. Skill version, schema version, bundle schema version, and report schema version are independent. A skill release does not automatically force every schema version to match the skill version. The current document/table/chunk schema version is `1.0`; see [VERSIONING.md](VERSIONING.md).

Every canonical element has fixed fields for hierarchy, content format, engine, confidence, source locator, properties, and warnings. Canonical tables preserve merge anchors in `cells` and provide a rectangular `grid` for CSV and downstream processing.

PDF/PPTX elements may include additive `properties.layout` and
`properties.associations` metadata. The exact fields, evidence thresholds, and
consumer rules are documented in
[`references/layout_association_contract.md`](references/layout_association_contract.md).

Chunks may include the additive `consumer_contract_version: "1.0"` projection:
validated ancestor/section/unit/relationship/layout IDs, context budget
accounting, and `embedding_text`. Canonical source `text` is never shortened to
make room for context. See
[`references/chunk_consumer_contract.md`](references/chunk_consumer_contract.md).

JSON Schemas are stored in `schemas/`. Format-specific granularity is documented in `references/capability_matrix.md`.

## Known boundaries

- Scanned table reconstruction is geometric and heuristic; complex borderless or merged tables may require a heavier parser.
- Tier-2 Docling/model accuracy and cross-platform runtime are not yet production-qualified; v1.9.0 validates the adapter contract and containment only.
- SmartArt and embedded OLE objects are detected and located but not expanded.
- Excel chart objects are represented as references; plotted series are not rendered in this release.
- Digital PDF and PPTX use deterministic geometry/placeholder-aware order; ambiguous visual intent remains warning-bearing and must be inspected.
- DOCX tracked changes, nested tables, and exact inline-image anchoring remain limited.
- Legacy binary Office files and round-trip conversion back to Office formats are out of scope.

## Development and release checks

```bash
python scripts/capability_probe.py --json
python scripts/check_release_consistency.py
python scripts/check_markdown_links.py
python scripts/build_skill_package.py --profile release --output dist --verify
python scripts/build_skill_package.py --profile agent-skill --output dist --verify
python scripts/validate_skill_package.py --profile release dist/universal-file-to-markdown-1.9.0-release.zip
python scripts/validate_skill_package.py --profile agent-skill dist/universal-file-to-markdown-1.9.0-skill.zip
python -m pytest tests/ -q
python -m compileall -q scripts tests
```

On Windows hosts where the user temp root is inaccessible, pass a unique repository-local `--basetemp` to pytest.

The full regression test suite is maintained in the source repository and is not included in the runtime release package or Agent Skill upload ZIP.

GitHub Actions are currently **manual-only** under the repository CI execution policy; run these checks locally or dispatch the documented manual workflows. Release-specific checks are documented in `RELEASING.md` and `RELEASE_CHECKLIST.md`.

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
