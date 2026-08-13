"""v1.9 optional Tier-2 adapter security and containment tests."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

import router
from ai_review import fingerprint
from tier2_adapter import derive_trigger_codes, run_tier2_candidate
from tier2_model_manifest import create_manifest, verify_manifest
from validate_bundle import validate_bundle


def _pdf_bundle(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    source = tmp_path / "source.pdf"
    canvas = Canvas(str(source), invariant=1)
    canvas.drawString(72, 720, "Native evidence remains authoritative")
    canvas.save()
    bundle = tmp_path / "bundle"
    report = router.convert(str(source), str(bundle))
    assert report["status"] == "passed"
    return source, bundle, report


def _model_manifest(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    (root / "weights.bin").write_bytes(b"offline-model-placeholder")
    create_manifest(root, "synthetic-docling-model", "test-1")
    return root / "tier2-model-manifest.json"


def _worker(tmp_path, mode="success"):
    path = tmp_path / f"worker-{mode}.py"
    if mode == "timeout":
        body = "import time\ntime.sleep(30)\n"
    elif mode == "failure":
        body = "import sys\nprint('contained failure', file=sys.stderr)\nsys.exit(7)\n"
    else:
        body = r'''import hashlib, json, pathlib, sys
request=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
out=pathlib.Path(request["output_dir"]); out.mkdir(parents=True,exist_ok=True)
document=out/"docling-document.json"; markdown=out/"document.md"
document.write_text(json.dumps({"body":{"children":[]},"texts":[],"tables":[],"pictures":[]}),encoding="utf-8")
markdown.write_text("# Tier-2 candidate\n",encoding="utf-8")
def artifact(path):
 data=path.read_bytes(); return {"path":path.name,"sha256":hashlib.sha256(data).hexdigest(),"size_bytes":len(data)}
manifest=pathlib.Path(request["model_manifest_path"])
result={"protocol_version":"1.0","status":"succeeded","adapter":{"name":"docling","version":"test-adapter"},"source_sha256":request["source_sha256"],"conversion_status":"success","model":{"model_id":"synthetic-docling-model","model_version":"test-1","manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest()},"security":{"remote_services_enabled":False,"external_plugins_enabled":False,"offline_environment_enforced":True},"artifacts":{"docling_document":artifact(document),"markdown":artifact(markdown)}}
(out/"worker-result.json").write_text(json.dumps(result),encoding="utf-8")
'''
    path.write_text(body, encoding="utf-8")
    return [sys.executable, str(path)]


def test_model_manifest_is_exact_and_detects_tampering(tmp_path):
    manifest_path = _model_manifest(tmp_path)
    manifest, errors = verify_manifest(manifest_path)
    assert not errors and manifest["files"][0]["path"] == "weights.bin"
    (manifest_path.parent / "weights.bin").write_bytes(b"tampered")
    assert "TIER2_MODEL_ARTIFACT" in " ".join(verify_manifest(manifest_path)[1])


def test_auto_gate_is_narrow_and_machine_readable():
    report = {"warnings": [{"code": "TABLE_STRUCTURE_UNVERIFIED"},
                           {"code": "FORMULA_RESULT_UNAVAILABLE"},
                           {"code": "READING_ORDER_UNCERTAIN"}],
              "details": {"ocr_table_candidates": [
                  {"reason_codes": ["OCR_TABLE_IRREGULAR_ROWS"]}
              ]}}
    assert derive_trigger_codes(report) == [
        "TABLE_STRUCTURE_UNVERIFIED", "OCR_TABLE_IRREGULAR_ROWS"
    ]


def test_default_router_does_not_create_tier2_sidecar(tmp_path):
    _source, bundle, report = _pdf_bundle(tmp_path)
    assert "tier2" not in report
    assert not (bundle / "tier2").exists()


def test_force_without_manifest_preserves_native_bundle(tmp_path):
    source, bundle, _report = _pdf_bundle(tmp_path)
    before = fingerprint(bundle)
    report = router.convert(str(source), str(bundle), tier2_policy="force")
    assert report["tier2"]["status"] == "unavailable"
    assert report["tier2"]["reason_codes"] == ["TIER2_MODEL_MANIFEST_REQUIRED"]
    assert fingerprint(bundle) == before
    assert validate_bundle(str(bundle))["status"] == "passed"


def test_unexpected_orchestrator_failure_is_recorded_without_cleanup(tmp_path, monkeypatch):
    source, bundle, _report = _pdf_bundle(tmp_path)
    original = (bundle / "document.json").read_bytes()
    monkeypatch.setattr("tier2_adapter.run_tier2_candidate",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    report = router.convert(str(source), str(bundle), tier2_policy="force")
    assert report["status"] == "passed"
    assert report["tier2"]["reason_codes"] == ["TIER2_INTERNAL_FAILURE"]
    assert (bundle / "document.json").read_bytes() == original
    assert validate_bundle(str(bundle))["status"] == "passed"


def test_auto_without_quality_signal_does_not_launch_worker(tmp_path):
    source, bundle, report = _pdf_bundle(tmp_path)
    result = run_tier2_candidate(
        str(source), str(bundle), report, policy="auto", model_manifest_path=None,
        worker_command=["command-that-must-not-run"],
    )
    assert result["status"] == "not_triggered"


def test_noneligible_format_never_launches_worker(tmp_path):
    source = tmp_path / "source.csv"; source.write_text("a,b\n1,2\n")
    bundle = tmp_path / "bundle"; report = router.convert(str(source), str(bundle))
    result = run_tier2_candidate(
        str(source), str(bundle), report, policy="force", model_manifest_path=None,
        worker_command=["command-that-must-not-run"],
    )
    assert result["status"] == "not_eligible"


def test_candidate_is_validated_but_never_selected_or_copied(tmp_path):
    source, bundle, report = _pdf_bundle(tmp_path)
    manifest = _model_manifest(tmp_path)
    native_document = (bundle / "document.json").read_bytes()
    before = fingerprint(bundle)
    result = run_tier2_candidate(
        str(source), str(bundle), report, policy="force",
        model_manifest_path=str(manifest), worker_command=_worker(tmp_path),
    )
    assert result["status"] == "candidate_available"
    assert result["selection"] == "native_retained_pending_manual_review"
    assert result["canonical_mutated"] is False
    assert result["native_bundle_fingerprint_before"] == before == fingerprint(bundle)
    assert (bundle / "document.json").read_bytes() == native_document
    assert (bundle / "tier2" / "candidate" / "docling-document.json").is_file()
    assert validate_bundle(str(bundle))["status"] == "passed"


def test_candidate_artifact_symlink_is_rejected_before_resolution(tmp_path, monkeypatch):
    source, bundle, report = _pdf_bundle(tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink",
        lambda self: self.name == "document.md" or original(self),
    )
    result = run_tier2_candidate(
        str(source), str(bundle), report, policy="force",
        model_manifest_path=str(_model_manifest(tmp_path)),
        worker_command=_worker(tmp_path),
    )
    assert result["status"] == "failed"
    assert result["reason_codes"] == ["TIER2_CANDIDATE_VALIDATION_FAILED"]


@pytest.mark.parametrize(("mode", "status", "code", "timeout"), [
    ("failure", "failed", "TIER2_ADAPTER_FAILED", 5.0),
    ("timeout", "timed_out", "TIER2_ADAPTER_TIMEOUT", 0.1),
])
def test_worker_failure_and_timeout_are_contained(tmp_path, mode, status, code, timeout):
    source, bundle, report = _pdf_bundle(tmp_path)
    manifest = _model_manifest(tmp_path)
    before = fingerprint(bundle)
    result = run_tier2_candidate(
        str(source), str(bundle), report, policy="force",
        model_manifest_path=str(manifest), worker_command=_worker(tmp_path, mode),
        timeout_seconds=timeout,
    )
    assert result["status"] == status and result["reason_codes"] == [code]
    assert fingerprint(bundle) == before
    assert validate_bundle(str(bundle))["status"] == "passed"


def test_standalone_validation_rejects_tier2_artifact_tampering(tmp_path):
    source, bundle, report = _pdf_bundle(tmp_path)
    result = run_tier2_candidate(
        str(source), str(bundle), report, policy="force",
        model_manifest_path=str(_model_manifest(tmp_path)),
        worker_command=_worker(tmp_path),
    )
    assert result["status"] == "candidate_available"
    (bundle / "tier2" / "candidate" / "document.md").write_text("tampered")
    validation = validate_bundle(str(bundle))
    assert validation["status"] == "failed"
    assert any("TIER2_CANDIDATE_ARTIFACT" in error for error in validation["errors"])
