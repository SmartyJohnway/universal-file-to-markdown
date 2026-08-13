import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ai_review import _schema, assess_ai_review_eligibility, prepare_request, validate_review


def _candidate():
    return {
        "candidate_id": "ocr-table-candidate-0007",
        "source_locator": {"format": "pdf", "page_start": 7, "page_end": 7},
        "confidence": 0.31,
        "decision": "fallback_to_text",
        "signals": {"row_count": 2, "column_count": 2},
        "reason_codes": [
            "OCR_TABLE_INSUFFICIENT_ROWS",
            "OCR_TABLE_LOW_CONFIDENCE",
            "OCR_TABLE_REJECTED",
            "OCR_TABLE_FALLBACK_TO_TEXT",
        ],
        "raw_text": "Model ABC-100\nVoltage 480 V",
    }


def _write_bundle(bundle: Path):
    bundle.mkdir()
    (bundle / "tables").mkdir()
    (bundle / "tables" / "index.json").write_text("[]\n", encoding="utf-8")
    (bundle / "manifest.json").write_text(
        json.dumps({"source_sha256": "a" * 64}), encoding="utf-8"
    )
    (bundle / "document.json").write_text(
        json.dumps({
            "elements": [{
                "id": "page-0007-text-001",
                "type": "text",
                "content": "Model ABC-100 Voltage 480 V",
                "source_locator": {"format": "pdf", "page": 7},
            }]
        }),
        encoding="utf-8",
    )
    (bundle / "chunks.jsonl").write_text("", encoding="utf-8")
    (bundle / "conversion-report.json").write_text(
        json.dumps({
            "status": "passed_with_warnings",
            "bundle_validation": {"status": "passed"},
            "warnings": [{"code": "OCR_TABLE_LOW_CONFIDENCE"}],
            "details": {"ocr_table_candidates": [_candidate()]},
        }),
        encoding="utf-8",
    )


def test_rejected_candidate_is_a_non_writable_advisory_without_canonical_table():
    report = {
        "status": "passed_with_warnings",
        "warnings": [{"code": "OCR_TABLE_LOW_CONFIDENCE"}],
        "details": {"ocr_table_candidates": [_candidate()]},
    }
    result = assess_ai_review_eligibility(report, [])
    assert result["recommended"] is True
    assert [target["target_type"] for target in result["targets"]] == ["advisory"]
    assert result["targets"][0]["projection_write_allowed"] is False
    assert result["targets"][0]["allowed_outcomes"] == ["needs_human_review", "no_change"]


def test_prepare_request_preserves_rejected_candidate_evidence_as_advisory(tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    request = prepare_request(bundle)
    assert len(request["targets"]) == 1
    target = request["targets"][0]
    assert target["target_type"] == "advisory"
    assert target["target_id"] == "advisory-ocr-table-candidate-0007"
    assert target["projection_write_allowed"] is False
    assert target["canonical"]["candidate_id"] == "ocr-table-candidate-0007"
    assert target["canonical"]["decision"] == "fallback_to_text"
    assert target["canonical"]["signals"]["row_count"] == 2
    assert "OCR_TABLE_REJECTED" in target["reason_codes"]
    assert target["allowed_outcomes"] == ["needs_human_review", "no_change"]


def test_rejected_candidate_advisory_accepts_only_declared_decisions(tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    request = prepare_request(bundle)
    review = {
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "source_sha256": request["source_sha256"],
        "canonical_bundle_fingerprint": request["canonical_bundle_fingerprint"],
        "reviewer": {"type": "host_ai", "provider": "test", "model": "test"},
        "review_status": "completed",
        "target_reviews": [{
            "target_id": request["targets"][0]["target_id"],
            "decision": "no_change",
            "confidence": 0.9,
            "operations": [],
            "notes": [],
            "uncertainties": [],
        }],
    }
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    assert validate_review(bundle, review_path)["status"] == "passed"

    review["target_reviews"][0]["decision"] = "apply_projection"
    review["target_reviews"][0]["readable_markdown"] = "Model ABC-100 Voltage 480 V"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    result = validate_review(bundle, review_path)
    assert "AI_REVIEW_DECISION_NOT_ALLOWED" in result["errors"]


def test_request_schema_rejects_non_decision_advisory_outcome(tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    request = prepare_request(bundle)
    request["targets"][0]["allowed_outcomes"] = ["needs_human_review", "no_action"]
    errors = _schema("ai-review-request.schema.json", request)
    assert any("no_action" in error for error in errors)


def test_rejected_candidate_advisory_refuses_projection_write(tmp_path):
    bundle = tmp_path / "bundle"
    _write_bundle(bundle)
    request = prepare_request(bundle)
    review = {
        "schema_version": "1.0",
        "request_id": request["request_id"],
        "source_sha256": request["source_sha256"],
        "canonical_bundle_fingerprint": request["canonical_bundle_fingerprint"],
        "target_reviews": [{
            "target_id": request["targets"][0]["target_id"],
            "decision": "apply_projection",
            "confidence": 0.9,
            "operations": [{"operation": "annotate_uncertain_structure"}],
            "readable_markdown": "Model ABC-100 Voltage 480 V",
        }],
    }
    review_path = tmp_path / "review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    result = validate_review(bundle, review_path)
    assert result["status"] == "failed"
    assert "AI_REVIEW_ADVISORY_TARGET_APPLY_UNSUPPORTED" in result["errors"]
