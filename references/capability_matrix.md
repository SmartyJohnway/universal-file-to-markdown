# Format capability matrix

Status vocabulary: `supported`, `supported_with_optional_dependency`, `partial`,
`experimental`, and `unsupported`. Qualification describes the implemented
route, not a promise of perfect visual reconstruction.

| Format | Route | Status | Dependency / fallback | Output | Known limitations | Qualification |
|---|---|---|---|---|---|---|
| DOCX | OOXML structural extraction | supported | python-docx + OOXML | hierarchical elements, tables, assets | tracked changes, nested tables, exact image anchoring | regression-covered |
| XLSX/XLSM | workbook extraction | supported | openpyxl | sheets, table blocks, references | chart series and dashboard semantics | regression-covered |
| PPTX | OOXML slide extraction | supported | python-pptx + OOXML | role/zone/column ordered slide/group elements, tables, assets | deterministic order cannot prove author intent; ambiguous flows emit `VISUAL_FLOW_AMBIGUOUS` | regression-covered |
| Digital PDF | text/table extraction | supported | PyMuPDF + pdfplumber | line-rebuilt page regions and bbox-positioned tables | strong two-column layouts use deterministic column-major order and still emit `READING_ORDER_UNCERTAIN`; irregular visual semantics remain limited | regression-covered |
| Scanned PDF | OCR route | partial | RapidOCR; Tesseract fallback | OCR regions and heuristic tables | complex, borderless, or merged tables | regression-covered containment cases |
| Raster images | OCR route | partial | RapidOCR; Tesseract fallback | OCR regions and heuristic tables | complex layout reconstruction | regression-covered containment cases |
| CSV/TSV | native parsing | supported | Python stdlib | canonical table | short samples can have ambiguous encodings | regression-covered |
| JSON | native parsing | supported | Python stdlib | structured block | no semantic domain inference | regression-covered |
| EML | native parsing | supported | Python stdlib | email and attachments | rich HTML styling | regression-covered |
| HTML/EPUB/RST/Org/TeX | Pandoc route | supported_with_optional_dependency | Pandoc; explicit failure if absent | structured block | installed reader capabilities | HTML regression-covered; other routes dependency-dependent |
| DOC/XLS/PPT | direct parsing | unsupported | convert to OOXML first | none | legacy binary formats | not offered |

All successful routes produce schema-validated `document.json` and
`chunks.jsonl`. Table-producing routes also write canonical table JSON, CSV,
merge-aware HTML, and `tables/index.json`.

PDF and PPTX elements may also expose the additive layout/association contract
documented in [layout_association_contract.md](layout_association_contract.md).
