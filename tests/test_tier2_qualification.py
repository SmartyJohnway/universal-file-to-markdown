"""v1.9.1 Tier-2 qualification evidence gates."""

import hashlib
import json
from pathlib import Path

from qualify_tier2 import _expectation_errors, _runs_are_deterministic, load_corpus, qualify
from tier2_model_manifest import create_manifest


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _corpus(tmp_path, documents=1):
    cases = []
    for index in range(documents):
        source = tmp_path / f"case-{index}.pdf"
        source.write_bytes(f"synthetic {index}".encode())
        cases.append({
            "case_id": f"case-{index}", "source_path": source.name,
            "sha256": _sha(source), "format": "pdf", "tags": ["smoke"],
            "expected": {"tier2_statuses": ["candidate_available"]},
        })
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"schema_version": "1.0", "corpus_id": "test", "documents": cases}),
                    encoding="utf-8")
    return path


def _manifest(tmp_path):
    root = tmp_path / "models"; root.mkdir()
    (root / "weights.bin").write_bytes(b"model")
    create_manifest(root, "test", "1")
    return root / "tier2-model-manifest.json"


def _passed_executor(item, _output, _manifest, **kwargs):
    runs = [{"tier2_status": "candidate_available"} for _ in range(kwargs["runs"])]
    return {"case_id": item["case_id"], "status": "passed", "deterministic": True,
            "runs": runs}


def test_corpus_loader_rejects_source_drift_and_escape(tmp_path):
    corpus = _corpus(tmp_path)
    data = json.loads(corpus.read_text())
    (tmp_path / "case-0.pdf").write_bytes(b"changed")
    assert "CORPUS_SOURCE_HASH_MISMATCH" in " ".join(load_corpus(corpus)[2])
    data["documents"][0]["source_path"] = "../escape.pdf"
    corpus.write_text(json.dumps(data))
    assert "CORPUS_SOURCE_PATH_ESCAPE" in " ".join(load_corpus(corpus)[2])


def test_smoke_pass_is_not_a_production_qualification(tmp_path):
    report = qualify(
        _corpus(tmp_path), _manifest(tmp_path), tmp_path / "out", mode="smoke", runs=1,
        timeout_seconds=10, document_timeout_seconds=5, max_num_pages=10,
        max_file_size_bytes=1024, executor=_passed_executor,
    )
    assert report["status"] == "passed"
    assert report["qualification_gate_status"] == "not_evaluated"
    assert report["production_qualified"] is False
    assert "MULTI_PLATFORM_EVIDENCE_REQUIRED" in report["production_blockers"]


def test_qualification_mode_fails_closed_on_small_uncovered_corpus(tmp_path):
    report = qualify(
        _corpus(tmp_path), _manifest(tmp_path), tmp_path / "out", mode="qualification", runs=2,
        timeout_seconds=10, document_timeout_seconds=5, max_num_pages=10,
        max_file_size_bytes=1024, executor=_passed_executor,
    )
    assert report["status"] == "failed"
    assert report["qualification_gate_status"] == "failed"
    assert "QUALIFICATION_REQUIRES_AT_LEAST_10_DOCUMENTS" in report["production_blockers"]
    assert any(value.startswith("QUALIFICATION_TAG_MISSING")
               for value in report["production_blockers"])


def test_candidate_expectations_are_explicit_and_machine_readable():
    actual = {"tier2_status": "candidate_available", "candidate_text_chars": 20,
              "candidate_tables": 0, "candidate_markdown": "hello evidence",
              "wall_duration_seconds": 3.0}
    expected = {"tier2_statuses": ["candidate_available"],
                "min_candidate_text_chars": 30, "min_candidate_tables": 1,
                "required_markdown_fragments": ["missing"],
                "required_reason_codes": ["EXPECTED_CODE"],
                "required_error_fragments": ["expected detail"],
                "max_duration_seconds": 2.0}
    assert _expectation_errors(actual, expected) == [
        "CANDIDATE_TEXT_COVERAGE_BELOW_MINIMUM",
        "CANDIDATE_TABLE_COUNT_BELOW_MINIMUM",
        "CANDIDATE_MARKDOWN_FRAGMENT_MISSING: missing",
        "TIER2_REASON_CODE_MISSING: EXPECTED_CODE",
        "TIER2_ERROR_FRAGMENT_MISSING: expected detail",
        "TIER2_DURATION_ABOVE_MAXIMUM",
    ]


def test_expected_non_candidate_runs_can_be_deterministic():
    failed = [{"tier2_status": "failed", "native_fingerprint": "a" * 64,
               "candidate_artifact_hashes": {}} for _ in range(2)]
    assert _runs_are_deterministic(failed, 2) is True
    failed[1]["tier2_status"] = "timed_out"
    assert _runs_are_deterministic(failed, 2) is False
