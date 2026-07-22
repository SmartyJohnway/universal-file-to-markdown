import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import capability_probe
import native_probe


def _result(returncode=0, stdout="", stderr=""):
    return native_probe.subprocess.CompletedProcess(["python"], returncode, stdout, stderr)


def test_probe_reports_required_dependency_missing(monkeypatch):
    real_find_spec = capability_probe.importlib.util.find_spec

    def fake_find_spec(name):
        if name == "rapidocr_onnxruntime":
            return None
        return real_find_spec(name)

    monkeypatch.setattr(capability_probe.importlib.util, "find_spec", fake_find_spec)
    result = capability_probe.probe()
    assert result["status"] == "failed"
    assert "rapidocr_onnxruntime" in result["missing_required"]


def test_probe_distinguishes_optional_system_binary(monkeypatch):
    monkeypatch.setattr(capability_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(capability_probe.shutil, "which", lambda _name: None)
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed"})
    result = capability_probe.probe()
    assert result["status"] == "passed"
    assert result["system_binaries"]["tesseract"] == {
        "available": False,
        "required": False,
    }


def test_native_probe_import_success(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_result(), False, 1))
    assert native_probe.probe_pymupdf()["import_status"] == "passed"


def test_native_probe_functional_pdf_success(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_result(), False, 1))
    result = native_probe.probe_pymupdf()
    assert result["status"] == "passed" and result["functional_status"] == "passed"


def test_native_probe_module_missing(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: None)
    assert native_probe.probe_pymupdf()["reason"] == "module_not_found"


def test_native_probe_import_error(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_result(2, stderr="bad import"), False, 1))
    assert native_probe.probe_pymupdf()["reason"] == "import_error"


def test_native_probe_nonzero_exit(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    calls = iter([(_result(), False, 1), (_result(3), False, 1)])
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: next(calls))
    assert native_probe.probe_pymupdf()["reason"] == "functional_open_failed"


def test_native_probe_signal_crash(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_result(-15), False, 1))
    result = native_probe.probe_pymupdf()
    assert result["reason"] == "native_dependency_crash" and result["signal"] == 15


def test_native_probe_timeout(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_result(None), True, 1))
    assert native_probe.probe_pymupdf()["reason"] == "dependency_probe_timeout"


def test_native_probe_parent_survives_child_crash(monkeypatch):
    monkeypatch.setattr(native_probe.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(native_probe, "_distribution_version", lambda: "1.26.4")
    monkeypatch.setattr(native_probe, "_run_child", lambda *_args: (_result(-7), False, 1))
    assert native_probe.probe_pymupdf()["status"] == "failed"


def test_capability_probe_fails_on_required_native_crash(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "failed", "reason": "native_dependency_crash"})
    result = capability_probe.probe()
    assert result["status"] == "failed" and "pymupdf" in result["missing_required"]


def test_capability_report_contains_environment(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed", "version": "1.26.4"})
    result = capability_probe.probe()
    assert result["environment"]["python_implementation"]


def test_capability_report_contains_package_version(monkeypatch):
    monkeypatch.setattr(capability_probe, "probe_pymupdf", lambda: {"status": "passed", "version": "1.26.4"})
    result = capability_probe.probe()
    assert result["python_modules"]["fitz"]["version"] == "1.26.4"
