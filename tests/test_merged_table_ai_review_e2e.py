"""End-to-end gate for cross-format merged-table AI Review triggering."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_merged_table_ai_review_regression import run


def test_merged_table_ai_review_trigger_e2e(tmp_path):
    summary = run(tmp_path / "merged-trigger-e2e")

    assert summary["case_count"] == 16
    assert summary["failed"] == 0, summary["results"]
    assert summary["validation_status"] == "passed"

    results_by_key = {(r["format"], r["merged"], r["mode"]): r for r in summary["results"]}

    for fmt in ("docx", "xlsx", "pptx", "html"):
        # 1. Merged Automatic (Positive)
        r_m_auto = results_by_key[(fmt, True, "automatic")]
        assert r_m_auto["status"] == "passed"
        assert "MERGED_TABLE_GEOMETRY_PRESENT" in r_m_auto["assessment_reason_codes"]
        assert "MERGED_TABLE_GEOMETRY_PRESENT" in r_m_auto["request_reason_codes"]
        assert r_m_auto["canonical_hashes_preserved"] is True

        # 2. Plain Automatic (Negative control)
        r_p_auto = results_by_key[(fmt, False, "automatic")]
        assert r_p_auto["status"] == "passed"
        assert "MERGED_TABLE_GEOMETRY_PRESENT" not in r_p_auto["assessment_reason_codes"]
        assert "MERGED_TABLE_GEOMETRY_PRESENT" not in r_p_auto["request_reason_codes"]
        assert "HTML_MERGED_TABLE_COMPLEX" not in r_p_auto["request_reason_codes"]
        assert r_p_auto["canonical_hashes_preserved"] is True

        # 3. Plain Explicit (Negative for false merged geometry reasons)
        r_p_exp = results_by_key[(fmt, False, "explicit")]
        assert r_p_exp["status"] == "passed"
        assert "EXPLICIT_USER_REQUEST" in r_p_exp["request_reason_codes"]
        assert "MERGED_TABLE_GEOMETRY_PRESENT" not in r_p_exp["request_reason_codes"]
        assert "HTML_MERGED_TABLE_COMPLEX" not in r_p_exp["request_reason_codes"]
        assert r_p_exp["canonical_hashes_preserved"] is True

        # 4. Merged Explicit (Positive for both explicit and merged reasons)
        r_m_exp = results_by_key[(fmt, True, "explicit")]
        assert r_m_exp["status"] == "passed"
        assert "EXPLICIT_USER_REQUEST" in r_m_exp["request_reason_codes"]
        assert "MERGED_TABLE_GEOMETRY_PRESENT" in r_m_exp["request_reason_codes"]
        if fmt == "html":
            assert "HTML_MERGED_TABLE_COMPLEX" in r_m_exp["request_reason_codes"]
        else:
            assert "HTML_MERGED_TABLE_COMPLEX" not in r_m_exp["request_reason_codes"]
        assert r_m_exp["canonical_hashes_preserved"] is True
