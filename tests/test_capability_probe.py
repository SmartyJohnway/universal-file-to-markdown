import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import capability_probe


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
    result = capability_probe.probe()
    assert result["status"] == "passed"
    assert result["system_binaries"]["tesseract"] == {
        "available": False,
        "required": False,
    }
