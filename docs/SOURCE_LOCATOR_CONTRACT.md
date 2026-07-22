# Source locator contract

Canonical elements and newly produced chunks carry `locator_precision`: `exact`,
`range`, `page_only`, `derived`, or `unknown`. `exact` identifies a source object
or explicit range; `range` combines source content; `page_only` identifies only a
PDF page; `derived` is OCR/layout-derived; and `unknown` deliberately makes no
location claim.

A chunk has `element_ids`, optional `table_ids`, and exactly one of
`source_locator` (one continuous source) or `source_locators` (non-contiguous
sources). Legacy schema 1.0 bundles may omit these optional provenance fields;
new converter output always provides `locator_precision`.

| Format | Locator fields |
| --- | --- |
| XLSX | `format`, `sheet_name`, `cell_range` (A1 notation); images may use `anchor_cell` |
| PPTX | `format`, `slide_number`, `shape_id` or `shape_ids` |
| PDF | `format`, `page_start`, `page_end`, optional `bboxes` |
| DOCX | `format`, `section_index`, `element_start`, `element_end` (`range`) |
| EML | `format`, `mime_part`, `section`, optional `filename` |
| CSV | `format`, 1-based physical `row_start`, `row_end` (header included) |
| JSON | `format`, `json_path` beginning with `$` |
| HTML/Pandoc | `unknown` unless a reliable block locator is available |

When compatible locators are aggregated, XLSX/CSV/DOCX ranges use a bounding
range, PPTX unions `shape_ids` on a slide, and adjacent PDF pages use a page
range. Otherwise chunks use `source_locators` and `range` precision. Validators
report stable provenance codes including `CHUNK_ELEMENT_REFERENCE_MISSING`,
`CHUNK_TABLE_REFERENCE_MISSING`, `CHUNK_LOCATOR_CONFLICT`,
`LOCATOR_PRECISION_INVALID`, and `INVALID_*` locator codes.
