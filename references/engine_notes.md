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

## Deliberately out of scope for this first version

- **PPTX merged-cell table renderer**: not built yet. PPTX tables use a
  different merge representation (`gridSpan`/`rowSpan`/`hMerge`/`vMerge`
  on `a:tc` elements in the slide XML) and merged cells are considerably
  less common in decks than in Word/Excel documents. Falls back to
  MarkItDown for now, which will flatten any merges it encounters.
- **Legacy binary formats** (`.doc`, `.xls`, `.ppt`): not parsed directly.
  These require either `LibreOffice --headless` conversion as a
  preprocessing step or OLE2-specific parsers, which is a meaningfully
  different engineering problem from the OOXML zip-based formats this
  skill focuses on.
- **Chart/embedded-object data extraction** (native Excel/PowerPoint
  charts, as opposed to raster images): the underlying chart XML
  (`xl/charts/chart1.xml`, etc.) is parseable but was judged lower
  priority than the two features this skill was built to solve
  (merged cells, OCR).
