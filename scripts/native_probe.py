"""Isolated runtime qualification for native Python dependencies.

The parent process deliberately imports neither PyMuPDF nor RapidOCR/OpenCV.
Every discovery, distribution-version lookup, import, and native smoke operation
is performed by the requested child interpreter.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import subprocess
import sys
import time
from typing import Sequence

DEFAULT_NATIVE_PROBE_TIMEOUT_SECONDS = 30.0


@dataclass
class NativeProbeResult:
    package: str
    module: str
    version: str | None
    status: str
    import_status: str
    functional_status: str
    return_code: int | None
    signal: int | None
    timed_out: bool
    stdout: str
    stderr: str
    duration_ms: int
    reason: str | None = None
    module_discovered: bool = False
    probe_mode: str = "subprocess"


def _run_child(command: Sequence[str], timeout_seconds: float) -> tuple[subprocess.CompletedProcess[str], bool, int]:
    started = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        return completed, False, int((time.monotonic() - started) * 1000)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(command, None, exc.stdout or "", exc.stderr or ""), True, int((time.monotonic() - started) * 1000)
    except OSError as exc:
        return subprocess.CompletedProcess(command, None, "", str(exc)), False, int((time.monotonic() - started) * 1000)


def _child_payload(stdout: str) -> dict | None:
    """Read the JSON protocol emitted by a child without trusting its parent."""
    try:
        return json.loads(stdout)
    except (TypeError, json.JSONDecodeError):
        return None


def _result(base: dict, **values: object) -> dict:
    result = asdict(NativeProbeResult(**base, **values))
    result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
    return result


def _version_supported(version: str | None) -> bool:
    if not version:
        return False
    try:
        major, minor, patch = (int(part) for part in version.split(".")[:3])
    except ValueError:
        return False
    return (major, minor, patch) >= (1, 26, 4) and (major, minor) < (1, 27)


_PYMUPDF_IMPORT = r'''import importlib.metadata as md
import importlib.util
import json
spec = importlib.util.find_spec("fitz")
result = {"module_discovered": spec is not None, "version": None, "error_message": None}
if spec is not None:
    try:
        result["version"] = md.version("PyMuPDF")
    except md.PackageNotFoundError:
        pass
    try:
        import fitz
    except Exception as exc:
        result["error_message"] = str(exc)
print(json.dumps(result))
'''
_PYMUPDF_FUNCTIONAL = r'''import json
try:
    import fitz
    doc = fitz.open(); doc.new_page(); payload = doc.tobytes(); doc.close()
    check = fitz.open(stream=payload, filetype="pdf")
    assert check.page_count == 1
    _ = check[0].rect
    check.close()
    print(json.dumps({"ok": True}))
except Exception as exc:
    print(json.dumps({"ok": False, "error_message": str(exc)}))
    raise
'''
_RAPIDOCR_IMPORT = r'''import importlib.metadata as md
import importlib.util
import json
spec = importlib.util.find_spec("rapidocr_onnxruntime")
result = {"module_discovered": spec is not None, "version": None, "error_message": None}
if spec is not None:
    try:
        result["version"] = md.version("rapidocr-onnxruntime")
    except md.PackageNotFoundError:
        pass
    try:
        import rapidocr_onnxruntime
        import cv2
    except Exception as exc:
        result["error_message"] = str(exc)
print(json.dumps(result))
'''
_RAPIDOCR_FUNCTIONAL = r'''import json
try:
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    image = np.full((24, 96, 3), 255, dtype=np.uint8)
    result, _ = RapidOCR()(image)
    assert result is None or isinstance(result, list)
    print(json.dumps({"ok": True}))
except Exception as exc:
    print(json.dumps({"ok": False, "error_message": str(exc)}))
    raise
'''


def _child_failure(base: dict, completed: subprocess.CompletedProcess[str], timed_out: bool, duration_ms: int, functional: bool = False) -> dict:
    if timed_out:
        reason, signal = "dependency_probe_timeout", None
    elif completed.returncode is None:
        reason, signal = "probe_internal_error", None
    elif completed.returncode < 0:
        reason, signal = "native_dependency_crash", -completed.returncode
    else:
        reason, signal = ("functional_open_failed" if functional else "import_error"), None
    return _result(base, status="failed", import_status="passed" if functional else reason,
                   functional_status=reason if functional else "not_run", return_code=completed.returncode,
                   signal=signal, timed_out=timed_out, stdout=completed.stdout or "", stderr=completed.stderr or "",
                   duration_ms=duration_ms, reason=reason)


def probe_pymupdf(
    python_executable: str = sys.executable,
    timeout_seconds: float = DEFAULT_NATIVE_PROBE_TIMEOUT_SECONDS,
) -> dict:
    """Qualify PyMuPDF in *python_executable*; child evidence is authoritative."""
    completed, timed_out, duration = _run_child([python_executable, "-c", _PYMUPDF_IMPORT], timeout_seconds)
    empty = {"package": "pymupdf", "module": "fitz", "version": None, "module_discovered": False}
    if timed_out or completed.returncode not in (0, None):
        return _child_failure(empty, completed, timed_out, duration)
    payload = _child_payload(completed.stdout)
    if payload is None:
        return _child_failure(empty, completed, False, duration)
    base = {**empty, "version": payload.get("version"), "module_discovered": bool(payload.get("module_discovered"))}
    if not base["module_discovered"]:
        return _result(base, status="failed", import_status="module_not_found", functional_status="not_run", return_code=completed.returncode, signal=None, timed_out=False, stdout=completed.stdout, stderr=completed.stderr, duration_ms=duration, reason="module_not_found")
    if payload.get("error_message"):
        return _result(base, status="failed", import_status="import_error", functional_status="not_run", return_code=completed.returncode, signal=None, timed_out=False, stdout=completed.stdout, stderr=completed.stderr, duration_ms=duration, reason="import_error")
    if not _version_supported(base["version"]):
        return _result(base, status="failed", import_status="passed", functional_status="not_run", return_code=completed.returncode, signal=None, timed_out=False, stdout=completed.stdout, stderr=completed.stderr, duration_ms=duration, reason="unsupported_version")
    functional, timed_out, functional_duration = _run_child([python_executable, "-c", _PYMUPDF_FUNCTIONAL], timeout_seconds)
    total = duration + functional_duration
    if timed_out or functional.returncode != 0:
        return _child_failure(base, functional, timed_out, total, functional=True)
    return _result(base, status="passed", import_status="passed", functional_status="passed", return_code=0, signal=None, timed_out=False, stdout=functional.stdout, stderr=functional.stderr, duration_ms=total)


def probe_rapidocr(
    python_executable: str = sys.executable,
    timeout_seconds: float = DEFAULT_NATIVE_PROBE_TIMEOUT_SECONDS,
) -> dict:
    """Qualify import, model construction, and one OCR inference in a child."""
    completed, timed_out, duration = _run_child([python_executable, "-c", _RAPIDOCR_IMPORT], timeout_seconds)
    empty = {"package": "rapidocr-onnxruntime", "module": "rapidocr_onnxruntime", "version": None, "module_discovered": False}
    if timed_out or completed.returncode not in (0, None):
        return _child_failure(empty, completed, timed_out, duration)
    payload = _child_payload(completed.stdout)
    if payload is None:
        return _child_failure(empty, completed, False, duration)
    base = {**empty, "version": payload.get("version"), "module_discovered": bool(payload.get("module_discovered"))}
    if not base["module_discovered"]:
        return _result(base, status="failed", import_status="module_not_found", functional_status="not_run", return_code=0, signal=None, timed_out=False, stdout=completed.stdout, stderr=completed.stderr, duration_ms=duration, reason="module_not_found")
    if payload.get("error_message"):
        return _result(base, status="failed", import_status="import_error", functional_status="not_run", return_code=0, signal=None, timed_out=False, stdout=completed.stdout, stderr=completed.stderr, duration_ms=duration, reason="import_error")
    functional, timed_out, functional_duration = _run_child([python_executable, "-c", _RAPIDOCR_FUNCTIONAL], timeout_seconds)
    total = duration + functional_duration
    if timed_out or functional.returncode != 0:
        return _child_failure(base, functional, timed_out, total, functional=True)
    return _result(base, status="passed", import_status="passed", functional_status="passed", return_code=0, signal=None, timed_out=False, stdout=functional.stdout, stderr=functional.stderr, duration_ms=total)
