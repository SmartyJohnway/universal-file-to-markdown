# v1.6 capability matrix

Use this matrix to judge the output's granularity. A check means the converter
emits the element or metadata deterministically; it does not promise visual
interpretation beyond the stated engine.

| Format | Parent unit | Fine elements | Table locator | Asset locator | Main disclosed gap |
|---|---|---|---|---|---|
| DOCX | document/heading | paragraph, list item, table | table index | inline positional image reference | tracked changes, nested tables, exact image relationship |
| PPTX | slide/group | title, paragraph, list, table, chart, image, note | slide + shape bbox | slide + shape ID + relationship | SmartArt/OLE content, unusual visual order |
| XLSX/XLSM | sheet | blank-separated table blocks, chart/image references | sheet + cell range | sheet reference | chart series rendering, complex dashboard semantics |
| PDF digital | page | heading/paragraph block, table | page + bbox | not yet a first-class image element | multi-column reading order |
| PDF scanned | page | OCR region, heuristic table | page; table bbox may be coarse | n/a | complex table/layout reconstruction |
| Raster image | image | OCR region, heuristic table | overall bbox | source image | complex layout reconstruction |
| CSV/TSV | document | table | table index | n/a | encoding may be ambiguous on short samples |
| JSON | document | structured block | n/a | n/a | no semantic domain inference |
| EML | document | email, attachment | n/a | sanitized attachment name | rich HTML styling |
| Pandoc inputs | document | structured block | engine-dependent | engine-dependent | depends on installed Pandoc readers |

All successful formats produce schema-validated `document.json` and
`chunks.jsonl`. Formats with tables also produce canonical table JSON, CSV,
merge-aware HTML, and `tables/index.json`.
