"""Phase 2 source-locator and chunk-provenance regression coverage."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from chunker import build_chunk_provenance
from validate_bundle import _valid_a1_range, _validate_source_locator


def _errors(locator):
    errors = []
    _validate_source_locator(locator, errors)
    return errors


def test_xlsx_chunk_inherits_sheet_cell_range_and_table_reference():
    element = {"table_id": "table-s001-b001", "locator_precision": "exact",
               "source_locator": {"format": "xlsx", "sheet_name": "Sheet1", "cell_range": "A1:G9"}}
    provenance = build_chunk_provenance([element], {})
    assert provenance["table_ids"] == ["table-s001-b001"]
    assert provenance["source_locator"]["cell_range"] == "A1:G9"
    assert provenance["locator_precision"] == "exact"


def test_pptx_multi_shape_and_multi_element_provenance():
    elements = [
        {"locator_precision": "exact", "source_locator": {"format": "pptx", "slide_number": 1, "shape_id": 5}},
        {"locator_precision": "exact", "source_locator": {"format": "pptx", "slide_number": 1, "shape_id": 7}},
    ]
    provenance = build_chunk_provenance(elements, {})
    assert provenance["locator_precision"] == "range"
    assert len(provenance["source_locators"]) == 2


def test_pdf_ocr_docx_csv_json_and_eml_precision_contracts():
    assert build_chunk_provenance([{"locator_precision": "derived", "source_locator": {"format": "pdf", "page_start": 1, "page_end": 1}}], {})["locator_precision"] == "derived"
    assert build_chunk_provenance([{"locator_precision": "range", "source_locator": {"format": "docx", "section_index": 0, "element_start": 1, "element_end": 2}}], {})["locator_precision"] == "range"
    assert not _errors({"format": "csv", "row_start": 1, "row_end": 2})
    assert not _errors({"format": "json", "json_path": "$.items[0]"})
    assert not _errors({"format": "eml", "mime_part": "1.2", "section": "attachment"})


def test_invalid_locator_fixtures_are_rejected_with_stable_codes():
    assert _errors({"format": "xlsx", "sheet_name": "Sheet1", "cell_range": "B2:A1"}) == ["INVALID_XLSX_CELL_RANGE"]
    assert "INVALID_PDF_PAGE_RANGE" in _errors({"format": "pdf", "page_start": 2, "page_end": 1})
    assert "INVALID_PDF_BBOX" in _errors({"format": "pdf", "page_start": 1, "page_end": 1, "bboxes": [[2, 1, 0, 4]]})
    assert "INVALID_PPTX_SLIDE_NUMBER" in _errors({"format": "pptx", "slide_number": 0})
    assert "INVALID_CSV_ROW_RANGE" in _errors({"format": "csv", "row_start": 2, "row_end": 1})
    assert "INVALID_JSON_PATH" in _errors({"format": "json", "json_path": "items[0]"})
    assert _valid_a1_range("$A$1:$G$9")
