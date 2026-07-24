import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import capability_probe
import native_probe


def _completed(code=0, payload=None, stderr=""):
    return native_probe.subprocess.CompletedProcess(["python"], code, json.dumps(payload or {}), stderr)


def _pymupdf_payload(version="1.26.4", discovered=True, error=None):
    return {"module_discovered": discovered, "version": version, "error_message": error}


def test_native_probe_import_success(monkeypatch):
    calls = iter([(_completed(payload=_pymupdf_payload()), False, 1), (_completed(payload={"ok": True}), False, 1)])
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: next(calls))
    assert native_probe.probe_pymupdf()["import_status"] == "passed"


def test_native_probe_functional_pdf_success(monkeypatch):
    calls = iter([(_completed(payload=_pymupdf_payload()), False, 1), (_completed(payload={"ok": True}), False, 1)])
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: next(calls))
    assert native_probe.probe_pymupdf()["functional_status"] == "passed"


def test_native_probe_module_missing(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(payload=_pymupdf_payload(discovered=False)), False, 1))
    assert native_probe.probe_pymupdf()["reason"] == "module_not_found"


def test_native_probe_import_error(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(payload=_pymupdf_payload(error="bad import")), False, 1))
    assert native_probe.probe_pymupdf()["reason"] == "import_error"


def test_native_probe_nonzero_exit(monkeypatch):
    calls = iter([(_completed(payload=_pymupdf_payload()), False, 1), (_completed(3, {"ok": False}), False, 1)])
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: next(calls))
    assert native_probe.probe_pymupdf()["reason"] == "functional_open_failed"


def test_native_probe_signal_crash(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(-15), False, 1))
    result = native_probe.probe_pymupdf()
    assert result["reason"] == "native_dependency_crash" and result["signal"] == 15


def test_native_probe_timeout(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(None), True, 1))
    assert native_probe.probe_pymupdf()["reason"] == "dependency_probe_timeout"


def test_native_probe_parent_survives_child_crash(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(-7), False, 1))
    assert native_probe.probe_pymupdf()["status"] == "failed"


def test_probe_uses_child_interpreter_discovery(monkeypatch):
    # Parent state is irrelevant: child JSON explicitly reports module absence.
    monkeypatch.setattr(native_probe, "_run_child", lambda command, *_args: (_completed(payload=_pymupdf_payload(discovered=False)), False, 1))
    assert native_probe.probe_pymupdf("child-python")["module_discovered"] is False


def test_probe_uses_child_interpreter_version(monkeypatch):
    calls = iter([(_completed(payload=_pymupdf_payload("1.26.7")), False, 1), (_completed(payload={"ok": True}), False, 1)])
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: next(calls))
    assert native_probe.probe_pymupdf("child-python")["version"] == "1.26.7"


def test_parent_child_version_mismatch(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(payload=_pymupdf_payload("1.27.0")), False, 1))
    assert native_probe.probe_pymupdf("child-python")["reason"] == "unsupported_version"


def test_parent_missing_child_available(monkeypatch):
    calls = iter([(_completed(payload=_pymupdf_payload()), False, 1), (_completed(payload={"ok": True}), False, 1)])
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: next(calls))
    assert native_probe.probe_pymupdf("child-python")["status"] == "passed"


def test_rapidocr_import_error_is_required_failure(monkeypatch):
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_completed(payload={"module_discovered": True, "version": "1.4.4", "error_message": "libGL.so.1: cannot open shared object file"}), False, 1))
    result = native_probe.probe_rapidocr()
    assert result["status"] == "failed" and result["reason"] == "import_error"


def test_capability_probe_fails_on_required_native_crash(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "failed", "reason": "native_dependency_crash"})
    monkeypatch.setattr(capability_probe, "probe_rapidocr", lambda: {"status": "passed"})
    assert "pymupdf" in capability_probe.probe()["missing_required"]


def test_capability_probe_fails_on_rapidocr_import_error(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed"})
    monkeypatch.setattr(capability_probe, "probe_rapidocr", lambda: {"status": "failed", "reason": "import_error"})
    assert capability_probe.probe()["status"] == "failed"


def test_capability_report_contains_environment(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed", "version": "1.26.4"})
    monkeypatch.setattr(capability_probe, "probe_rapidocr", lambda: {"status": "passed"})
    assert capability_probe.probe()["environment"]["python_implementation"]


def test_capability_report_contains_package_version(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed", "version": "1.26.4"})
    monkeypatch.setattr(capability_probe, "probe_rapidocr", lambda: {"status": "passed"})
    assert capability_probe.probe()["python_modules"]["fitz"]["version"] == "1.26.4"


def test_capability_probe_optional_dependency_disclosure(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed", "version": "1.26.4"})
    monkeypatch.setattr(capability_probe, "probe_rapidocr", lambda: {"status": "passed"})
    result = capability_probe.probe()
    assert "markitdown" in result["python_modules"]
    assert result["python_modules"]["markitdown"]["required"] is False
    assert "affected_routes" in result
    assert "missing_optional_dependencies" in result

