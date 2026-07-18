---
name: universal-file-to-markdown
description: Convert PDF, Word (.docx), Excel (.xlsx/.xlsm), CSV, JSON, EML, and markup files (HTML/EPUB/etc via Pandoc) into clean, AI-ready Markdown. Specializes in two things most generic converters get wrong — merged-cell tables in Excel and Word (rendered as real HTML rowspan/colspan, not flattened) and OCR for scanned PDFs/images (via a fully offline, ~15MB bundled model, no external model download required). Use this skill whenever the user asks to convert a document to Markdown, extract text/tables from a spreadsheet or Word file, OCR a scanned PDF, or "turn this file into something an AI/RAG pipeline can use." Always use this instead of ad-hoc conversion code when the input is one of the supported formats.
---

# Universal File to Markdown

Deterministic-first document conversion. Every converter here is either
pure structural parsing (openpyxl / python-docx XML / pdfplumber) or a
small, fully offline model (RapidOCR). Nothing in this skill depends on
downloading model weights from the network at runtime — that dependency
was tested and found to fail in network-restricted sandboxes (see
`references/engine_notes.md` for the empirical basis of this design).

## When to use this skill

Use it for:
- "Convert this Excel/Word/PDF file to Markdown"
- "Extract the tables from this spreadsheet, including the merged cells"
- "OCR this scanned PDF / image"
- "Turn this into something I can feed to an LLM / RAG pipeline"
- Any file with the extensions: `.xlsx`, `.xlsm`, `.docx`, `.pdf`, `.csv`,
  `.tsv`, `.json`, `.eml`, `.html`, `.epub`

Do NOT reach for a from-scratch script for these formats — the converters
here already handle the two hard cases (merged cells, OCR) correctly and
report quality issues instead of silently degrading.

## How to run it

```bash
python3 scripts/router.py <input_file> --output <output_dir>
```

This produces a bundle in `<output_dir>`:

```
document.md              # the converted Markdown
manifest.json            # source hash, file type, conversion timestamp
conversion-report.json   # status + any warnings (see below)
assets/                  # embedded images/media, if any were extracted
```

**Always read `conversion-report.json` after converting and surface its
`status` and `warnings` to the user** — do not just hand over
`document.md` and call it done. If `status` is `"failed"` or
`"passed_with_warnings"`, tell the user what the warning means in plain
language before presenting the file. This is the core design principle of
this skill: no silent success.

## Format-by-format behavior

| Format | Engine | Handles merged cells? | Handles OCR? |
|---|---|---|---|
| `.xlsx` / `.xlsm` | `xlsx_converter.py` (openpyxl) | Yes — exact, via `merged_cells.ranges` | n/a |
| `.docx` | `docx_converter.py` (python-docx + raw OOXML) | Yes — both horizontal (`gridSpan`) and vertical (`vMerge`) | n/a |
| `.pdf` (digital, has text layer) | `pdf_converter.py` → pdfplumber | Table cell detection via ruling lines | No OCR needed |
| `.pdf` (scanned / image-based) | `pdf_converter.py` → RapidOCR | Bounding-box heuristic only (see limitation below) | Yes, offline, incl. Chinese |
| `.csv` / `.tsv` | native (stdlib `csv`) | n/a | n/a |
| `.json` | native (stdlib `json`) | n/a | n/a |
| `.eml` | native (stdlib `email`) | n/a | n/a |
| `.html`, `.epub`, `.rst`, `.org`, `.tex` | Pandoc (subprocess) | n/a | n/a |
| `.pptx` | MarkItDown fallback | No (out of scope, see engine_notes.md) | n/a |
| `.xls`, `.doc`, `.ppt` (legacy binary) | Not supported | — | — convert to the modern format first (e.g. LibreOffice headless), then re-run |

## Pre-flight checks the router always does

1. **Encryption/password check first** — for Office files via
   `msoffcrypto-tool` (or a zip-open heuristic if that package isn't
   installed), for PDFs via PyMuPDF's `is_encrypted`. If a file is
   password-protected, conversion stops immediately with
   `status: "failed", reason: "password_protected"` instead of letting a
   downstream parser fail confusingly or silently return garbage.
2. **Encoding detection for text formats** (CSV/plain text) via
   `charset-normalizer` — never assumes UTF-8 first. This matters
   specifically for Traditional Chinese users: legacy CSV/TXT exports
   from older systems are very often Big5, not UTF-8, and assuming UTF-8
   produces mojibake without the sniff step.

## Known, stated limitations (read before promising results to the user)

- **Scanned Latin-script pages could come out glued together
  ("eTotalAmount") — now auto-detected and auto-corrected.** RapidOCR's
  bundled recognition model is trained for CJK text (no inter-word
  spacing to begin with), so on English/Latin content it sometimes
  transcribes several words inside one detection box as a single glued
  string. The router now checks the actual recognized text for this
  signature (an internal lower→upper case transition like `eTotalAmount`,
  or unusually long tokens) and, if the page is also majority-Latin
  script, automatically re-OCRs that page with Tesseract instead (word-
  granularity detection, no gluing problem). CJK pages are untouched and
  keep using RapidOCR, which is the right tool for that content. Which
  engine actually produced each page's final text is recorded in
  `engine_per_page` in the report — always check `MISSING_WORD_SPACING`
  and `TESSERACT_FALLBACK_USED` warnings if present.
- **Scanned tables now get a real (if heuristic) structure pass.**
  A column-clustering step looks for x-coordinates that repeat across
  several lines and, if found, renders that region as an actual Markdown
  table instead of flattened reading-order text. This is a bounding-box
  heuristic, not a trained table-structure model — it works well for
  simple ruled/aligned tables and can miss complex, borderless, or
  heavily merged layouts. `table_regions_detected` and the
  `TABLE_STRUCTURE_HEURISTIC` / `TABLE_STRUCTURE_UNVERIFIED` warnings
  tell you which case applied to a given document — tell the user this
  means "text is reliable, table shape should be spot-checked" only in
  the `UNVERIFIED` case; the `HEURISTIC` case means a table WAS built and
  should be spot-checked for column alignment rather than assumed to be
  entirely missing.
- **PPTX** does not yet have a custom merged-cell-aware table renderer
  (falls back to MarkItDown). This is a smaller gap than xlsx/docx because
  merged cells are far less common in PPTX tables, but it means a
  complex PPTX table may lose structure. Flag this if the input has
  visibly merged table cells.
- **Legacy binary formats** (`.xls`, `.doc`, `.ppt`) are not converted
  directly — tell the user to save-as the modern format first.
- **This skill intentionally does not use Docling / MinerU / Marker.**
  Those give better scanned-table structure than the RapidOCR heuristic
  path above, but require a multi-GB torch install and a Hugging Face
  model download that is blocked in this kind of sandboxed environment.
  If a user's document genuinely needs that level of table fidelity and
  they have access to a less-constrained environment (their own server,
  a self-hosted agent), point them to `references/engine_notes.md` for
  the Tier-2 escalation path rather than silently giving them a
  lower-fidelity result and calling it final.

## Reference files

- `references/engine_notes.md` — why each engine was chosen, what was
  empirically tested, and the Tier-2 (Docling/MinerU) escalation path for
  environments that can support it.
