---
name: universal-file-to-markdown
description: Convert PDF, scanned images, Word (.docx), Excel (.xlsx/.xlsm), PowerPoint (.pptx), CSV/TSV, JSON, EML, and Pandoc-supported markup into clean Markdown plus schema-validated canonical elements, bounded RAG chunks, tables, assets, manifest, and an explicit quality report. Use when an AI conversation needs to read, normalize, OCR, inspect, or prepare supported files for analysis/RAG, especially Traditional Chinese Big5/CP950 data, merged Office tables, mixed digital/scanned PDFs, or documents requiring traceable page/sheet/slide/shape locators. Prefer this deterministic offline-first workflow before escalating low-confidence or unsupported structures to a heavier parser.
---

# Universal File to Markdown v1.7.0-dev

Convert supported files with deterministic structural parsers and offline OCR.
Never treat `document.md` alone as proof of success: inspect the quality report
and bundle validation result every time.

## Run

Install Python dependencies from `requirements.txt`. Tesseract and Pandoc are
optional system binaries used only for their documented paths.

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
| `.pptx` | python-pptx + OOXML | slide/group/title/paragraph/list/table/chart/image/note | bullet inheritance, exact picture relationship, stable asset names |
| digital PDF pages | PyMuPDF + pdfplumber | page + located text blocks/tables | table text de-duplication, bbox locators |
| scanned PDF pages | RapidOCR; Tesseract fallback | page + OCR region/table | per-page OCR confidence and table likelihood |
| PNG/JPEG/TIFF/BMP/WebP | RapidOCR; Tesseract fallback | OCR region/table | direct offline image OCR |
| CSV/TSV | stdlib CSV | canonical table | UTF-8 first, then Traditional-Chinese-aware encoding scoring |
| JSON | stdlib JSON | structured block | pretty-printed Unicode JSON |
| EML | stdlib email | email + attachment elements | sanitized collision-safe attachment names |
| HTML/EPUB/RST/Org/TeX | Pandoc | structured block | fails explicitly when Pandoc is absent |

`.doc`, `.xls`, and `.ppt` are not parsed directly. Convert them to modern
OOXML first, then rerun.

## Canonical contracts

Skill version and data schema version are different:

```text
skill_version: 1.7.0-dev
document/table/chunk schema_version: 1.0
```

Every canonical element has fixed keys including `parent_id`, `children`,
`content_format`, `heading_path`, `engine`, `confidence`, normalized
`source_locator`, `properties`, and `warnings`. Format-specific values may
remain as additional fields for backward compatibility.

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
- PPTX visual reading order is top/left geometry and can be wrong for unusual
  overlapping or multi-flow layouts.
- DOCX tracked-change semantics, nested tables, and exact relationship-based
  inline image anchoring remain limited; inspect the original when material.
- Legacy binary Office and round-trip conversion back to Office are out of
  scope.

Read `references/engine_notes.md` only when investigating engine choice,
historical defects, or escalation. Run `python3 -m pytest tests/ -q` before
shipping any modification, and require a passing capability probe in the
release environment.
