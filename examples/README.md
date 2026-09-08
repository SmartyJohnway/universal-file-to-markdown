# Universal File to Markdown Examples

This directory contains concrete, reproducible conversion showcases generated using the stable v1.8.2 converter and validated against canonical schemas.

Each example demonstrates the evidence-first design: how inputs are processed into `document.md`, structured canonical representations, bounded RAG chunks, and a definitive conversion quality report.

---

## Showcase 1: Normal Success (DOCX)

- **Directory:** [`01_normal_docx/`](01_normal_docx/)
- **Input:** [`01_normal_docx/input/docx_basic.docx`](01_normal_docx/input/docx_basic.docx) (synthetic test document with bold and italic styling)
- **Engine:** `docx_native` (python-docx + OOXML)
- **Status:** `passed` (`bundle_validation.status: passed`, 0 warnings)

### What it proves
- Clean conversion path where text formatting is faithfully rendered in Markdown (`**bold*** italic*`).
- Generates canonical element hierarchy in `document.json` with precise source locators.
- Emits bounded RAG chunk in `chunks.jsonl` with full source locator metadata (`element_start: 1, element_end: 1, section_index: 0`).

---

## Showcase 2: Warning & Uncertainty Disclosure (CSV with Big5 Encoding)

- **Directory:** [`02_warning_encoding_big5/`](02_warning_encoding_big5/)
- **Input:** [`02_warning_encoding_big5/input/big5.csv`](02_warning_encoding_big5/input/big5.csv) (Traditional Chinese text encoded in Big5)
- **Engine:** `csv_native` (Python stdlib CSV with multi-candidate encoding scoring)
- **Status:** `passed_with_warnings`

### What it proves
- **Failure-aware transparency:** Instead of silently guessing or hallucinating characters, the converter scores multiple encoding candidates (`big5: 1.0`, `cp950: 1.0`, `gb18030: 0.917`) and discloses ambiguity via warning code `ENCODING_AMBIGUOUS`.
- The output Markdown preserves an HTML comment annotation indicating the chosen encoding: `<!-- source_encoding: big5 -->`.
- Extracts a canonical table with standalone CSV and HTML assets in `tables/`.

---

## Showcase 3: Structural Fidelity (XLSX Merged Cells)

- **Directory:** [`03_structural_fidelity_xlsx/`](03_structural_fidelity_xlsx/)
- **Input:** [`03_structural_fidelity_xlsx/input/xlsx_merged.xlsx`](03_structural_fidelity_xlsx/input/xlsx_merged.xlsx) (Excel worksheet containing merged header cells `A1:B1`)
- **Engine:** `xlsx_native` (openpyxl)
- **Status:** `passed` (`bundle_validation.status: passed`)

### What it proves
- **Merged table preservation:** Preserves merged table geometry by generating merge-aware HTML tables with `colspan="2"`:
  ```html
  <table>
  <tr>
  <td colspan="2">Header</td>
  </tr>
  <tr>
  <td>A</td>
  <td>1</td>
  </tr>
  </table>
  ```
- Emits canonical table JSON retaining cell coordinates, merge anchors, and dimensions alongside standalone `.csv` and `.html` asset representations in `tables/`.

---

## Running the Examples

You can reproduce these outputs locally by running the router against any of the input files:

```bash
# Example 1: DOCX
python scripts/router.py examples/01_normal_docx/input/docx_basic.docx --output /tmp/docx_out
python scripts/validate_bundle.py /tmp/docx_out

# Example 2: CSV Big5
python scripts/router.py examples/02_warning_encoding_big5/input/big5.csv --output /tmp/csv_out
python scripts/validate_bundle.py /tmp/csv_out

# Example 3: XLSX Merged
python scripts/router.py examples/03_structural_fidelity_xlsx/input/xlsx_merged.xlsx --output /tmp/xlsx_out
python scripts/validate_bundle.py /tmp/xlsx_out
```
