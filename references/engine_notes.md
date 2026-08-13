# Engine notes: why these choices, and what was actually tested

This skill was deliberately designed around **lightweight, structural, or
fully-offline engines** instead of a single heavy "AI document understanding"
engine (Docling / MinerU / Marker). This was not a default choice — it
follows from concrete tests run in a network-restricted sandbox
(equivalent to a typical Claude Skill execution environment).

## What was tested and why Docling/MinerU were rejected as the primary path

1. **Disk footprint**: `pip install docling` pulls in `torch`,
   `torchvision`, `transformers`, `accelerate`, and related packages.
   In a test with ~7.4GB of available disk, the install failed partway
   with `OSError: [Errno 28] No space left on device` — `torch` alone
   was 1.2GB before the install even got to Docling's own packages.

2. **Network dependency**: Docling/MinerU download model weights from
   Hugging Face Hub at first run. In a network-restricted sandbox:
   ```
   curl -I https://huggingface.co
   → HTTP/2 403, x-deny-reason: host_not_allowed
   ```
   Even if the pip install succeeded, the first real conversion call
   would fail or hang trying to fetch model weights.

3. **Conclusion**: any skill that lists Docling/MinerU as the *default*
   engine will silently fail or degrade in exactly this kind of
   environment, and worse, may do so *silently* if the calling code
   doesn't distinguish "install failed" / "model download blocked" /
   "parse failed" — which is a real risk if error handling only wraps
   the final `.convert()` call.

## What was tested and confirmed to work instead

| Library | Install size | Network at runtime | Verified |
|---|---|---|---|
| `openpyxl` | negligible | none | merged-cell ranges read directly and reconstructed as HTML `rowspan`/`colspan` — exact, not inferred |
| `python-docx` (+ raw OOXML access) | negligible | none | horizontal (`gridSpan`) and vertical (`vMerge`) merges both read directly from XML and reconstructed correctly |
| `pdfplumber` + PyMuPDF (`fitz`) | ~25MB (PyMuPDF wheel) | none | digital-PDF text and ruled-table extraction |
| `rapidocr-onnxruntime` | **14.9MB wheel**, models bundled inside (3 ONNX files, ~15.5MB total: detection, recognition incl. Chinese, orientation classifier) | **none** — no Hugging Face call, `onnxruntime` already satisfies its only heavy dependency | ran OCR end-to-end offline in ~3 seconds including model init |
| Pandoc | pre-installed in this sandbox (3.1.3) | none | should still be capability-checked (`which pandoc`) on other execution environments since it may not be preinstalled elsewhere |
| `charset-normalizer` | negligible (already a MarkItDown dependency) | none | correctly round-tripped Big5-encoded Traditional Chinese text |
| `msoffcrypto-tool` | 114KB | none | encryption detection for Office files |

## Tier-2 escalation path (for environments without these constraints)

If you're running this skill (or a fork of it) inside an environment with:
- full outbound network access (specifically `huggingface.co` reachable), and
- several GB of free disk / a persistent volume for model caching

...then Docling or MinerU genuinely do better on the hardest case this
skill is honest about being weak on: **complex or borderless tables inside
scanned PDFs**. In that case:

1. Run this skill's router first regardless — the encryption check,
   format detection, and native handlers (csv/json/eml) are all still
   useful.
2. For the specific case of `file_type == "pdf"` with
   `report.details.table_structure_confidence == "low"`, hand the same
   input file to a separately-hosted Docling/MinerU service (e.g. a
   Docker container with a persistent model-cache volume, not reinstalled
   per-request) and use its table output instead.
3. Do not swap this in as the default path inside this skill's own
   sandbox — that reintroduces the disk/network failure mode this design
   avoids. Keep it as an explicit, separate escalation step, and keep the
   reported `status` honest about which engine actually produced the
   final table.

## v1.7.3 truthfulness hardening

v1.7.3 remains warning-only for layout intelligence. Digital PDF block geometry can emit `MULTI_COLUMN_LAYOUT_DETECTED`, `READING_ORDER_UNCERTAIN`, and, when tables share the page, `TABLE_TEXT_ASSOCIATION_UNCERTAIN`; it does not claim to have corrected the order. PPTX overlap or independent side-by-side flows emit `VISUAL_FLOW_AMBIGUOUS` while retaining the established top/left projection.

Rejected OCR table candidates are not canonical tables. They now become explicit non-writable AI Review `advisory` targets carrying candidate decision evidence, rather than being mislabeled as an `element_range` through the generic fallback path.

Native PyMuPDF/RapidOCR probes remain isolated in child processes. Their default per-child timeout is 30 seconds and can be overridden with `capability_probe.py --native-timeout-seconds`; this contains crashes while avoiding a 10-second cold-start/contention false failure observed on Windows.

## Real-world validation round (post-v1): three bugs found and fixed

After v1 shipped, a real mixed Chinese/English scanned document (with a
fee table) was run through the skill and reviewed by inspecting
`pdf_converter.py`'s actual logic against the observed bad output, rather
than just re-running until it looked fine. Three root causes were found
and fixed — this section exists so a future change to this file doesn't
accidentally regress any of them.

1. **Glued words on Latin-script content.** RapidOCR's recognition model
   is CJK-tuned and doesn't predict inter-word spaces; when a single
   detection box actually spans multiple English words, they come out
   glued (`"eTotalAmount"`, `"Pleaseremit"`). v1's line-joining logic only
   added spaces *between* boxes, which can't fix a gluing problem that
   happens *inside* one box's recognized text.
   - Fix: `_looks_glued()` inspects the actual recognized text per page
     (not a page-wide average, which a real test case showed gets diluted
     to nothing by ordinary short words) for camelCase-style transitions
     and implausibly long tokens. If a page trips this AND is
     majority-Latin script, it's automatically re-OCR'd with Tesseract
     (word-granularity detection, no gluing problem), and the report
     records which engine produced each page's final text
     (`engine_per_page`).
   - **A page-wide average token length is not a reliable signal.**
     Verified case: `['eTotalAmount'(12 chars), 'Pleaseremit'(11), 'Due'(3),
     'Today'(5), 't'(1), '30'(2), 'days'(4), ...]` → page average ≈5.8,
     below any sane single threshold, even though the page clearly had a
     gluing problem. Detection has to look at individual tokens.

2. **No table detection on the scanned path.** The digital-PDF path uses
   `pdfplumber.find_tables()`; the scanned path had no equivalent and
   poured every OCR box through pure reading-order reconstruction, which
   silently misaligns multi-column tables (a fee table on the test
   document came out as unaligned running text).
   - Fix: `_cluster_into_table()` clusters OCR box x-coordinates into
     candidate column boundaries and checks whether that pattern repeats
     across enough lines to be a real table. If so, the region is
     rendered as an actual Markdown table; if not, it falls back to the
     original line-by-line reconstruction. Verified against a synthetic
     4-row/3-column box layout — correctly reconstructed the table with
     headers and all four data rows in the right columns.

3. **The warning system checked which code path ran, not what the output
   actually contained.** v1 put a blanket `TABLE_STRUCTURE_UNVERIFIED`
   warning on every scanned page regardless of whether it had a table,
   and average OCR confidence (0.94, high) didn't catch the glued-word
   problem because RapidOCR was *confident* about its wrong transcription
   — confidence measures the model's certainty in its own output, not
   whether that output is correct.
   - Fix: `quality_check.py` now emits `MISSING_WORD_SPACING` only when
     the glued-token heuristic actually fires, `TESSERACT_FALLBACK_USED`
     when the fallback engine ran, `TABLE_STRUCTURE_HEURISTIC` when a
     table WAS reconstructed (spot-check alignment) vs.
     `TABLE_STRUCTURE_UNVERIFIED` only when no table pattern was found at
     all. These are content-derived signals, not "which function was
     called" signals.

None of this makes the scanned-OCR path a substitute for a real
table-structure model on genuinely complex/borderless layouts — see the
Tier-2 escalation path above for that case. What changed is that the
*common* failure mode (English text glued together, simple ruled tables
misaligned) is now caught and, for the glue case, actually fixed rather
than just flagged.

## v1.2: correctness hardening (external review + verification cycle)

An external review of v1.1 raised several correctness concerns. Per this
project's practice, each was reproduced before being fixed - all three
reproduced as described:

1. **PDF digital/scanned misclassification at the document level.** A
   30-ish-character digital PDF fell under a 50-char whole-document
   threshold and got routed to OCR unnecessarily. Fixed: classify per
   page (any extractable text -> digital), with a genuine mixed-mode path
   for documents with both digital and scanned pages.
2. **Big5 CSV misdetected as UTF-16BE**, producing legal-but-wrong
   Unicode (not caught by mojibake checks, since the output was valid
   Unicode, just wrong), reported as `status: passed`. Fixed: strict
   UTF-8 first, then plausibility-scored candidates instead of trusting a
   single statistical detector.
3. **Excel formula cells with no cached value rendered as silent blanks**,
   reported as `status: passed`. Fixed: every cell resolved through a
   formula-aware function that preserves the formula text and reports
   `FORMULA_RESULT_UNAVAILABLE` instead of an unexplained empty cell.

Also added: magic-byte/container-based format detection (an extension
lying about the real format no longer sends a file to the wrong parser -
verified with an .xlsx renamed to .pdf, which openpyxl's own filename
validation additionally required a temp-path workaround for), tri-state
encryption checking (`encrypted`/`not_encrypted`/`unknown` - a parser
error is never silently treated as "safe"), and EML attachment filename
sanitization (a `../../evil.bin` attachment name is neutralized before
ever touching a real path).

## v1.3: canonical representation and provenance

Added `document.json` (element list: one entry per sheet/page/paragraph/
table/slide, with engine and confidence where applicable), `chunks.jsonl`
(heading/unit-aware chunking - a sheet, page, or slide is a natural chunk
boundary, not a blind character count, which routinely cuts a table away
from the paragraph explaining it), and `tables/*.csv`+`*.html` (every
detected table also as a standalone asset, for direct loading into
pandas/etc. rather than parsing it back out of embedded Markdown).

This is a deliberately smaller schema than Docling's DoclingDocument - no
per-run bounding boxes, no reading-order graph. The goal is "enough
structure for a RAG pipeline to know what page/sheet/slide something came
from and which engine produced it," not a full document object model.

## v1.4: Office fidelity

**DOCX**: run-level bold/italic/bold-italic via `paragraph.iter_inner_content()`
(which interleaves `Run` and `Hyperlink` objects in true document order -
verified with a manually-constructed `w:hyperlink` XML element, since
this python-docx version has no direct "add a hyperlink" convenience
method); hyperlinks rendered as Markdown links; nested lists via explicit
`w:numPr`/`w:ilvl` or, failing that, the trailing digit in python-docx's
own "List Bullet 2"/"List Bullet 3" style names; footnotes/endnotes
extracted directly from `word/footnotes.xml`/`word/endnotes.xml` (not a
first-class API in this python-docx version - verified against a manually
constructed footnote fixture built via raw zip/XML injection, since
python-docx itself has no way to create one either); header/footer
paragraphs; inline images anchored at their actual position in the text
flow (previously: a single trailing comment listing all extracted media,
with no indication of where in the document each one belonged).

**XLSX**: date/datetime cells render as ISO dates instead of Python's
default datetime repr; hyperlinks as Markdown links; cell comments
collected per-sheet; workbook-level defined names listed in the report;
chart presence counted (not rendered - see below); **used-region
trimming** - iterate only cells with actual content instead of trusting
`ws.max_row`/`max_column`, which openpyxl can report as inflated by
formatting-only cells with no data.

**Bug the test suite caught during this work**: the used-region trimming
initially checked only the `data_only=True` workbook for non-None values
to find sheet bounds - but a formula cell with no cached value has `value
== None` in that workbook, so it was excluded from the "used" region
entirely, meaning it was never rendered or counted. This silently
undid the v1.2 formula-preservation fix for exactly the case that fix was
built for. Caught by `test_missing_cached_value_is_not_silent_blank`
before being shipped - this is the concrete argument for the pytest suite
existing at all: a manual spot-check with an older fixture could plausibly
have missed this, since the bug only manifests when used-region trimming
and formula handling interact.

## v1.5.1: correctness patch (external review + verification cycle)

Prompted by an external review of v1.5 that judged it `PASS_WITH_CAVEATS`
- the core architecture and v1.1-v1.5 fixes held up, but flagged six
concrete correctness/disclosure gaps in the PPTX converter and the
document.json/table-export output contract. All six were fixed and each
has a dedicated regression test in `tests/test_router.py`
(`*V151` test classes).

1. **PPTX level-0 bullets were silently downgraded to plain paragraphs.**
   The v1.5 renderer treated `para.level > 0` as "is a bullet" and
   anything at level 0 as plain text - but level 0 IS PowerPoint's
   ordinary top-level bullet indentation. An everyday flat bulleted list
   (the single most common case on a real slide) lost its list semantics
   entirely and rendered as plain paragraphs. Fixed by reading the
   paragraph's own `<a:pPr>` bullet markup directly
   (`_get_bullet_info()` in `pptx_converter.py`): `<a:buNone/>` -> not a
   bullet, `<a:buAutoNum/>` -> numbered, `<a:buChar/>` -> bulleted with
   that character, and no explicit override -> still bulleted (matching
   PowerPoint's own body-placeholder default). Full inheritance
   resolution from the slide layout/master's bullet definitions is still
   not attempted - a paragraph that doesn't explicitly set or unset a
   bullet is assumed bulleted, which is correct for the common case but
   could theoretically be wrong for an unusual master that overrides the
   default to no-bullet. Flagged as a possible v1.6 follow-up if it ever
   surfaces in practice.

   **Superseded in v1.6.0:** this paragraph describes the v1.5.1 behavior.
   v1.6.0 resolves explicit paragraph settings first, then layout/master
   inheritance for body-like placeholders, while ordinary text boxes default
   to prose. See the current v1.6.0 section below.

2. **SmartArt/embedded-OLE presence was a silent drop, not a disclosed
   limitation.** SKILL.md described SmartArt/OLE as "out of scope,
   noted, not silently dropped" but nothing in `conversion-report.json`
   actually reflected whether a given input contained any - every real
   file with a SmartArt diagram or an embedded Excel object looked
   identical, in its report, to one without. Fixed by scanning the pptx
   zip container's own relationship parts (`ppt/slides/_rels/*.rels` for
   `.../relationships/diagramData` and `.../relationships/oleObject`
   relationship types, corroborated by `ppt/diagrams/*.xml` presence) and
   surfacing counts as `smartart_parts_found`/`ole_objects_found` in the
   converter report, which `quality_check.py` turns into
   `SMARTART_NOT_EXTRACTED`/`EMBEDDED_OLE_NOT_EXTRACTED` warnings
   (status escalates to `passed_with_warnings`). Content extraction
   itself is still out of scope - this is detection + disclosure only.

3. **Group-nested tables were discarded before reaching `tables_out`.**
   `_render_shape()`'s group-shape branch had a comment claiming it would
   "surface the first" nested table, but the code actually returned
   `None` unconditionally for the table slot - so a table inside a group
   shape rendered correctly into `document.md`'s Markdown but its
   standalone `tables/*.csv+*.html` asset never existed, for ANY
   group-nested table, not just the 2nd+. Fixed by changing
   `_render_shape()`'s return contract from a single optional table dict
   to a `tables: list`, which the group branch now accumulates from every
   recursed sub-shape instead of dropping.

4. **Standalone `tables/*.html` silently flattened merge geometry that
   `document.md` preserved.** DOCX/XLSX/PPTX converters all compute
   correct rowspan/colspan for merged cells and render them into
   `document.md` correctly - but only ever passed a flat `rows` grid to
   `table_export.py`, which rebuilt standalone HTML from that flat grid
   with no span information at all. So `document.md` and
   `tables/table-0001.html` for the exact same table could show different
   structure. Fixed by having each converter also emit a `cells` list
   (`{row, col, value, rowspan, colspan}`, one entry per merge-anchor or
   unmerged cell) alongside `rows`; `table_export.py` renders standalone
   HTML from `cells` when present, falling back to the old flat-grid
   renderer otherwise. `rows`/CSV still flattens spans (CSV has no way to
   express a span - an accepted, documented limitation, not a bug).
   While fixing this, also found and fixed a related XLSX-only bug: the
   grid passed to `tables_out` for a merged sheet was RAGGED (spanned-over
   cells were skipped instead of leaving a blank placeholder), producing
   a non-rectangular CSV with a different column count per row depending
   on how many merges that row happened to touch.

5. **`document.json` elements didn't reliably expose `engine`/
   `confidence`/`source_locator`.** SKILL.md documents the canonical
   element schema as including these "where applicable", but in practice
   a DOCX paragraph element had neither key at all, a PDF page element
   had both, and no element type had `source_locator`. Fixed in
   `document_model.py`: every element is now normalized to the same
   top-level keys before being written to `document.json` - missing
   `engine` falls back to the converter's own reported engine (passed
   through from `router.py`), missing `confidence`/`source_locator`
   default to `null` rather than being absent. This was the interim
   v1.5.1 contract; v1.6 subsequently introduced schema 1.0 and finer
   format-specific child elements.

6. **`TABLE_STRUCTURE_UNVERIFIED` was a blanket warning, not a real
   likelihood check.** The v1.5 code's comment claimed it would "only
   warn when the page actually looked tabular but clustering couldn't
   confirm it," but the actual condition just checked whether
   `table_regions_detected == 0` - true for EVERY scanned page with no
   detected table, including a plain scanned prose letter with zero
   tabular content. `table_structure_confidence` was hardcoded to the
   string `"low"` in that same branch, so it carried no real signal.
   Fixed by adding `_estimate_table_likelihood()` to `pdf_converter.py`:
   a real per-page heuristic score (column-position repetition, row/column
   fill ratio, box density) computed even when `_cluster_into_table`'s
   stricter thresholds (>=3 rows, >=2 confirmed columns) weren't met.
   `quality_check.py` now only raises `TABLE_STRUCTURE_UNVERIFIED` when
   `table_likelihood >= 0.4` AND no table was actually detected - a plain
   prose scan no longer gets a table-related warning at all.

None of these six required touching the v1.1-v1.5 fixes already locked in
by the existing 15 tests, which still pass unmodified.

## v1.5: PPTX custom converter

Replaced the v1.1-v1.4 MarkItDown fallback for `.pptx` with a converter
built on python-pptx, which - unlike DOCX/XLSX - exposes table merges
through a clean first-class API (`cell.is_merge_origin`, `is_spanned`,
`span_width`, `span_height`) rather than requiring raw-XML digging.
Covers: title/body text reading order (shapes sorted by top/left
position - a heuristic approximation of visual reading order, not a
guarantee for unusual layouts), merge-aware tables, images (extracted via
the same OOXML-zip media mechanism as DOCX/XLSX), chart title/category/
series data (via `shape.chart` - verified against a real generated
column chart), speaker notes, and group shapes (recursed into).

**Deliberately out of scope**: SmartArt diagrams (stored as separate
diagram-data XML, not exposed as readable text through python-pptx),
embedded OLE objects (e.g. an Excel range embedded inside a slide), and
run-level bold/italic within slide text boxes (slide text is usually
short titles/bullets where this matters less than in a Word document
body - could be added later following the same pattern as the DOCX
renderer if a real need comes up).

## Test suite

`tests/` is a real pytest suite (not just this file's development notes)
- `conftest.py` generates every fixture programmatically (no committed
binary files), and `test_router.py` asserts on the *specific* behavior
each historical bug represents, not just "doesn't crash." Run before
trusting any change to a converter:

```bash
python3 -m pytest tests/ -v
```



## v1.6.0: canonical contracts and integrated validation

v1.6 freezes document/table/chunk schema version 1.0 independently of the
skill version. It adds fixed element fields and parent/child references,
shape-level PPTX elements, blank-separated XLSX blocks, located digital-PDF
text blocks, direct raster-image OCR, source-rich bounded chunks, and a common
table contract. `validate_bundle.py` checks schemas plus tree reachability and
cycles, root/count invariants, chunk identity/count/index consistency, and table
dimensions/cell bounds; the router runs it automatically before reporting
success. A rerun clears only known bundle artifacts first so stale canonical
outputs cannot survive a failure.

OOXML preflight classifies the container before checking encryption: valid ZIP
packages, corrupt/invalid OOXML, and OLE-based encrypted Office files are
distinct outcomes. Standalone image provenance records
`rapidocr_onnxruntime` or `tesseract` according to the actual OCR path.

The v1.5.1 bullet patch was also corrected: absence of paragraph bullet XML is
not itself evidence of a bullet. Explicit `buNone`/`buChar`/`buAutoNum` wins;
body-like placeholders then resolve layout/master level styles; ordinary text
boxes default to prose.

## Deliberately out of scope (current, as of v1.6.0)

- **Legacy binary formats** (`.doc`, `.xls`, `.ppt`): not parsed directly.
  These require either `LibreOffice --headless` conversion as a
  preprocessing step or OLE2-specific parsers, which is a meaningfully
  different engineering problem from the OOXML zip-based formats this
  skill focuses on.
- **Excel native chart data extraction**: chart presence is counted in
  the report but not rendered - the underlying chart XML
  (`xl/charts/chart1.xml`) is parseable but was judged lower priority
  than the features this skill was built to solve. (PPTX charts, by
  contrast, ARE extracted - `shape.chart` in python-pptx made that
  straightforward enough to include in v1.5; the same effort for Excel's
  chart XML would be a separate, larger piece of work.)
- **SmartArt diagram content and embedded OLE object content** in PPTX
  are still not extracted (see v1.5 notes above) - as of v1.5.1, their
  PRESENCE is now detected and disclosed in the conversion report (see
  the v1.5.1 changelog above), which is a meaningfully different claim
  than actually extracting the diagram/object's content.
- **DOCX/XLSX/PPTX -> DOCX/XLSX/PPTX round-tripping**: this skill only
  converts TO Markdown/JSON, never back to Office formats.
- **Canonical granularity is deterministic rather than visually semantic.**
  PPTX shapes and XLSX blank-separated blocks are explicit, and digital PDF
  blocks carry bounding boxes, but complex dashboards, overlapping slide
  flows, and multi-column PDF reading order are not inferred by a layout model.
- **The 2,000-character chunk limit is hard.** Large pipe tables repeat their
  headers. A pathological individual row longer than the limit is split at a
  word or character boundary because preserving both the row and hard limit is
  impossible.
