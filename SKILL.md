---
name: universal-file-to-markdown
version: 1.8.0
release_status: development
description: >
  Convert PDF, scanned images, DOCX, XLSX/XLSM, PPTX, CSV/TSV, JSON,
  EML, and supported markup into traceable Markdown and validated
  canonical bundles. Use this skill when users ask to extract,
  convert, inspect, preserve, validate, translate, audit, or prepare
  document content for AI review, RAG, or downstream automation.
license: Apache-2.0
compatibility: Requires Python 3.10–3.12; Python 3.11 recommended.
---

# Universal File to Markdown v1.8.0

Convert supported files with deterministic structural parsers and offline OCR.
Never treat `document.md` alone as proof of success: inspect the quality report
and bundle validation result every time.

## Run

Install Python dependencies from `requirements.txt`. Supported Python is 3.10–3.12; Python 3.11 is the primary qualified runtime, and Python 3.13 is not currently supported. RapidOCR is declared as `rapidocr-onnxruntime>=1.4,<2` and qualified at 1.4.4. Pandoc is optional: it is not required for the core profile and is required only for Pandoc-enabled routes.

On Linux, OpenCV/RapidOCR may require `libGL.so.1`; install Tesseract only when using the `pytesseract` fallback. On Windows, OpenCV may require the Microsoft Visual C++ runtime, and the Tesseract executable must be installed and discoverable when that fallback is used.

Verify the environment before conversion. Missing required Python dependencies
produce an explicit non-zero preflight result; optional binaries are reported
without failing the probe:

```bash
python3 scripts/capability_probe.py --json
```

```bash
python3 scripts/router.py <input_file> --output <output_directory>
```

If a short legacy text file is reported as `ENCODING_AMBIGUOUS`, inspect the
candidate list and rerun with an explicit codec rather than trusting a plausible
but potentially wrong CJK decode:

```bash
python3 scripts/router.py input.csv --output output --encoding gb18030
```

The command exits non-zero when the final report status is `failed`.

Read these outputs:

```text
document.md              backward-compatible Markdown
document.json            canonical hierarchical elements (schema 1.0)
chunks.jsonl              locator-rich chunks; hard maximum 2,000 characters
tables/                   canonical JSON plus CSV and merge-aware HTML
assets/                   extracted images and attachments
manifest.json             source SHA-256, versions, timestamp, final status
conversion-report.json   engine details, warnings, and bundle validation
```

The router removes only known prior bundle artifacts before a rerun. A failed
rerun cannot leave stale `document.json`, chunks, tables, or assets from an
older successful conversion.

## Required completion check

1. Read `conversion-report.json`.
2. Surface `status` and every warning in plain language.
3. Confirm `bundle_validation.status` is `passed` for a successful bundle.
4. If needed, rerun validation independently:

```bash
python3 scripts/validate_bundle.py <output_directory>
```

Do not present canonical/RAG outputs when conversion or bundle validation
failed. Preserve `document.md`, `manifest.json`, and the failure report for
diagnosis.

## Format behavior

| Input | Primary engine | Canonical granularity | Important behavior |
|---|---|---|---|
| `.docx` | python-docx + OOXML | heading/paragraph/list item/table | bold/italic, links, notes, headers/footers, merged cells |
| `.xlsx`, `.xlsm` | openpyxl | sheet + blank-separated table blocks + chart/image references | formulas, large tables, comments, merged cells, hidden-state metadata |
| `.pptx` | python-pptx + OOXML | slide/group/title/paragraph/list/table/chart/image/note | role/column order, bullet inheritance, exact picture relationship |
| digital PDF pages | PyMuPDF + pdfplumber | page + located text blocks/tables | line-aware XY-cut order, bbox table insertion, de-duplication |
| scanned PDF pages | RapidOCR; Tesseract fallback | page + OCR region/table | per-page OCR confidence and table likelihood |
| PNG/JPEG/TIFF/BMP/WebP | RapidOCR; Tesseract fallback | OCR region/table | direct offline image OCR |
| CSV/TSV | stdlib CSV | canonical table | UTF-8 first, then Traditional-Chinese-aware encoding scoring |
| JSON | stdlib JSON | structured block | pretty-printed Unicode JSON |
| EML | stdlib email | email + attachment elements | sanitized collision-safe attachment names |
| HTML/EPUB/RST/Org/TeX | Pandoc | structured block | fails explicitly when Pandoc is absent |

`.doc`, `.xls`, and `.ppt` are not parsed directly. Convert them to modern
OOXML first, then rerun.

## Canonical contracts

Skill version, schema version, bundle schema version, and report schema version are independent. A skill release does not automatically force every schema version to match the skill version:

```text
skill_version: 1.8.0 (development)
published_stable_version: 1.7.2
document/table/chunk schema_version: 1.0
```

Every canonical element has fixed keys including `parent_id`, `children`,
`content_format`, `heading_path`, `engine`, `confidence`, normalized
`source_locator`, `properties`, and `warnings`. Format-specific values may
remain as additional fields for backward compatibility.

Located PDF and PPTX elements may carry additive `properties.layout` hints
(`reading_order`, region, column, layout zone, confidence, and method).
Strong-evidence caption/table/figure and speaker-note/slide edges use
`properties.associations`. These hints do not change schema 1.0 or claim that
the author's semantic intent is known. See
`references/layout_association_contract.md`.

Every canonical table contains `dimensions`, merge-anchor `cells`, a
rectangular `grid`, source locator, confidence, and engine. HTML is rendered
from cells and preserves row/column spans. CSV uses the rectangular grid and
therefore records that merges are flattened.

Chunks use leaf elements, inherit source locators, and include source file,
page/sheet/slide bounds, element IDs, character count, and split-part indexes.
Oversized content is split at paragraphs/rows/lines before word-safe hard
splitting. Large Markdown tables repeat their header in subsequent chunks.

JSON Schemas are in `schemas/`. Read `references/capability_matrix.md` when
deciding whether a format's canonical granularity is sufficient for the task.
For AI Review request generation, validation, and projection rendering, see
[ai_review_workflow.md](references/ai_review_workflow.md).

## Quality interpretation

- `passed`: conversion and bundle validation succeeded without detected loss.
- `passed_with_warnings`: usable output with specifically disclosed uncertainty
  or unsupported content; explain each warning.
- `failed`: do not treat canonical outputs as valid.

Common warnings include formula results unavailable, ambiguous encoding, low
OCR confidence, likely-but-unreconstructed scanned tables, SmartArt/OLE content
not extracted, and Excel charts represented only as references.

## Boundaries and escalation

- Scanned table reconstruction is geometric and heuristic. Escalate complex,
  borderless, merged, or low-confidence scans to the Tier-2 options described
  in `references/engine_notes.md` when the environment supports their models.
- SmartArt and embedded OLE content are detected and located but not expanded.
- Excel chart objects are detected as canonical references; plotted series are
  not rendered in this release.
- Digital PDF and PPTX use deterministic geometry/role-aware ordering. Strong
  columns are ordered column-major; ambiguous visual semantics still emit
  `READING_ORDER_UNCERTAIN` or `VISUAL_FLOW_AMBIGUOUS` and require inspection.
- DOCX tracked-change semantics, nested tables, and exact relationship-based
  inline image anchoring remain limited; inspect the original when material.
- Legacy binary Office and round-trip conversion back to Office are out of
  scope.

Read `references/engine_notes.md` only when investigating engine choice,
historical defects, or escalation. Run `python3 -m pytest tests/ -q` before
shipping any modification, and require a passing capability probe in the
release environment.
