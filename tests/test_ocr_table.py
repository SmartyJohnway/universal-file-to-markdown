import sys
sys.path.insert(0, 'scripts')
from ocr_table import assess_ocr_table

def boxes(rows):
    return [([[x,y * 20],[x+10,y * 20],[x+10,y * 20+8],[x,y * 20+8]], text, .9) for y, row in enumerate(rows) for x, text in row]

def test_label_value_lines_are_not_table():
    c=assess_ocr_table(boxes([[(0,'Name: Alice')],[(0,'Department: Engineering')],[(0,'Status: Active')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text' and 'OCR_TABLE_KEY_VALUE_PATTERN' in c['reason_codes']
def test_colon_sentences_are_not_table():
    c=assess_ocr_table(boxes([[(0,'Note: important information.')],[(0,'Warning: do not disconnect power.')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text'
def test_clear_aligned_table_is_accepted():
    c=assess_ocr_table(boxes([[(0,'Item'),(100,'Quantity')],[(0,'Motor'),(100,'2')],[(0,'Pump'),(100,'4')],[(0,'Valve'),(100,'12')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'accepted' and c['confidence'] >= .6 and c['signals']['column_count'] == 2
def test_two_sparse_rows_rejected():
    c=assess_ocr_table(boxes([[(0,'Model'),(100,'ABC-100')],[(0,'Voltage'),(100,'480 V')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text' and 'OCR_TABLE_INSUFFICIENT_ROWS' in c['reason_codes']
def test_irregular_columns_rejected():
    c=assess_ocr_table(boxes([[(0,'Item'),(60,'Qty'),(120,'Price')],[(0,'Motor'),(60,'2')],[(0,'Pump'),(120,'4'),(180,'800')],[(0,'Remark: spare unit')]]), 1, 'rapidocr', 'x')
    assert c['decision'] == 'fallback_to_text'


def test_mixed_pdf_propagates_ocr_candidate_metrics(monkeypatch):
    import pdf_converter
    scanned_report = {"ocr_avg_confidence": .9, "ocr_table_candidates": [{"candidate_id": "c"}],
                      "ocr_table_assessment": {"candidate_count": 1, "accepted_count": 1,
                      "rejected_count": 0, "fallback_to_text_count": 0, "low_confidence_count": 0}}
    monkeypatch.setattr(pdf_converter, "_convert_digital", lambda *args: {"_per_page_md": ["digital"], "report": {"table_count": 0}, "elements": [], "tables": []})
    monkeypatch.setattr(pdf_converter, "_convert_scanned", lambda *args: {"_per_page_md": ["scanned"], "report": scanned_report, "elements": [], "tables": []})
    result = pdf_converter._convert_mixed("unused", [None, None], ["digital", "scanned"])
    assert result["report"]["ocr_table_candidates"] == scanned_report["ocr_table_candidates"]
    assert result["report"]["ocr_table_assessment"] == scanned_report["ocr_table_assessment"]


def test_regression_runner_reports_expected_results(tmp_path):
    import subprocess, sys
    runner = __import__("pathlib").Path(__file__).parents[1] / "scripts" / "run_ocr_table_regression.py"
    completed = subprocess.run([sys.executable, str(runner), "--output", str(tmp_path)], capture_output=True, text=True)
    summary = __import__("json").loads((tmp_path / "ocr-table-regression-summary.json").read_text())
    assert completed.returncode == 0
    assert summary["validation_status"] == "passed"
    assert all(result["passed"] for result in summary["results"])


def test_validator_rejects_invalid_ocr_metadata_and_locator():
    from validate_bundle import _validate_table_semantics
    table = {"id": "ocr", "dimensions": {"rows": 1, "columns": 2}, "grid": [["a", "b"]], "cells": [],
             "source_format": "pdf", "source_locator": {"format": "pdf", "page_start": 0, "page_end": 0},
             "confidence": 2, "engine": "", "properties": {"origin": "ocr_table_candidate", "decision": "fallback_to_text"}}
    errors = []; _validate_table_semantics(table, errors)
    assert {"OCR_TABLE_REJECTED_AS_CANONICAL", "OCR_TABLE_CONFIDENCE_INVALID", "OCR_TABLE_DECISION_INVALID", "OCR_TABLE_LOCATOR_INVALID"}.issubset(errors)


def test_validator_rejects_ocr_metrics_mismatch(tmp_path):
    from validate_bundle import _validate_ocr_table_metrics
    report = {"details": {"ocr_table_assessment": {"candidate_count": 1, "accepted_count": 1, "rejected_count": 1, "fallback_to_text_count": 0, "low_confidence_count": 0}}}
    errors = []; _validate_ocr_table_metrics(report, set(), str(tmp_path), errors)
    assert "OCR_TABLE_METRICS_MISMATCH" in errors
