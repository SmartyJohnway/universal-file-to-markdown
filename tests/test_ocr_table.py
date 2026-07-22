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


def _write_ocr_bundle(tmp_path, accepted, monkeypatch):
    import hashlib
    import validate_bundle
    monkeypatch.setattr(validate_bundle, "_schema_validate", lambda *_args: None)
    from router import _write_bundle
    source = tmp_path / "source.pdf"; source.write_bytes(b"synthetic")
    candidate = {"candidate_id": "ocr-table-candidate-0001", "source_locator": {"format": "pdf", "page_start": 1, "page_end": 1},
                 "confidence": .9 if accepted else .2, "decision": "accepted" if accepted else "fallback_to_text",
                 "signals": {"row_count": 3}, "reason_codes": [] if accepted else ["OCR_TABLE_REJECTED", "OCR_TABLE_FALLBACK_TO_TEXT"]}
    assessment = {"candidate_count": 1, "accepted_count": int(accepted), "rejected_count": int(not accepted),
                  "fallback_to_text_count": int(not accepted), "low_confidence_count": int(not accepted)}
    rows = [["Item", "Qty"], ["Motor", "2"], ["Pump", "4"]]
    elements = [{"id": "page-0001", "type": "page", "page": 1, "content": "page", "engine": "rapidocr", "source_locator": {"page": 1}},
                {"id": "page-0001-content", "parent_id": "page-0001", "type": "table" if accepted else "text",
                 "content": "table" if accepted else "Name: Alice", "engine": "rapidocr", "source_locator": {"page": 1},
                 **({"table_id": "table-ocr-p0001-0001"} if accepted else {})}]
    tables = [{"id": "table-ocr-p0001-0001", "rows": rows, "source_locator": {"format": "pdf", "page_start": 1, "page_end": 1},
               "engine": "rapidocr", "confidence": .9, "properties": {"origin": "ocr_table_candidate", "candidate_id": candidate["candidate_id"], "decision": "accepted", "signals": candidate["signals"]}}] if accepted else []
    output = tmp_path / ("accepted" if accepted else "rejected")
    output.mkdir()
    _write_bundle(str(output), str(source), "pdf", hashlib.sha256(source.read_bytes()).hexdigest(),
                  "| Item | Qty |\n| --- | --- |\n| Motor | 2 |" if accepted else "Name: Alice",
                  {"status": "passed", "engine": "rapidocr_onnxruntime", "ocr_used": True,
                   "ocr_table_candidates": [candidate], "ocr_table_assessment": assessment}, elements=elements, tables=tables)
    return output


def test_accepted_ocr_candidate_becomes_one_valid_canonical_table(tmp_path, monkeypatch):
    bundle = _write_ocr_bundle(tmp_path, True, monkeypatch)
    index = __import__("json").loads((bundle / "tables" / "index.json").read_text())
    report = __import__("json").loads((bundle / "conversion-report.json").read_text())
    assert len(index) == 1
    assert report["bundle_validation"]["status"] == "passed"
    assert report["details"]["ocr_table_assessment"]["accepted_count"] == 1


def test_rejected_ocr_candidate_has_no_canonical_table_or_chunk_reference(tmp_path, monkeypatch):
    bundle = _write_ocr_bundle(tmp_path, False, monkeypatch)
    document = __import__("json").loads((bundle / "document.json").read_text())
    chunks = [__import__("json").loads(line) for line in (bundle / "chunks.jsonl").read_text().splitlines()]
    report = __import__("json").loads((bundle / "conversion-report.json").read_text())
    assert not (bundle / "tables" / "index.json").exists()
    assert not any(element["type"] == "table" for element in document["elements"])
    assert not any(chunk.get("table_ids") for chunk in chunks)
    assert report["bundle_validation"]["status"] == "passed"
    assert report["details"]["ocr_table_assessment"]["fallback_to_text_count"] == 1
