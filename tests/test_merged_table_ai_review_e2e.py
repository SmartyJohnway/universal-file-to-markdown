"""End-to-end gate for cross-format merged-table AI Review triggering."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_merged_table_ai_review_regression import run


def test_merged_table_ai_review_trigger_e2e(tmp_path):
    summary = run(tmp_path / "merged-trigger-e2e")

    assert summary["case_count"] == 8
    assert summary["positive_case_count"] == 4
    assert summary["negative_case_count"] == 4
    assert summary["failed"] == 0, summary["results"]
    assert summary["validation_status"] == "passed"

    positives = {result["format"]: result for result in summary["results"] if result["merged"]}
    negatives = {result["format"]: result for result in summary["results"] if not result["merged"]}
    assert set(positives) == {"docx", "xlsx", "pptx", "html"}
    assert set(negatives) == {"docx", "xlsx", "pptx", "html"}

    for result in positives.values():
        assert result["status"] == "passed"
        assert "MERGED_TABLE_GEOMETRY_PRESENT" in result["assessment_reason_codes"]
        assert "MERGED_TABLE_GEOMETRY_PRESENT" in result["request_reason_codes"]
        assert result["canonical_table_ids"]
        assert set(result["request_target_ids"]) & set(result["canonical_table_ids"])
        assert result["canonical_hashes_preserved"] is True

    for result in negatives.values():
        assert result["status"] == "passed"
        assert "MERGED_TABLE_GEOMETRY_PRESENT" not in result["assessment_reason_codes"]
        assert "MERGED_TABLE_GEOMETRY_PRESENT" not in result["request_reason_codes"]
        assert result["canonical_hashes_preserved"] is True
