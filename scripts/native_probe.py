"""Isolated runtime qualification for native Python dependencies.

This module deliberately never imports :mod:`fitz`.  PyMuPDF imports and PDF
operations execute in child interpreters, so a native crash is reported rather
than taking down the capability-probe process.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
import time
from typing import Sequence


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


IMPORT_SMOKE = "import fitz\nprint(getattr(fitz, '__version__', None) or '')\n"
FUNCTIONAL_SMOKE = """import fitz
doc = fitz.open()
doc.new_page()
payload = doc.tobytes()
doc.close()
check = fitz.open(stream=payload, filetype='pdf')
assert check.page_count == 1
_ = check[0].rect
check.close()
print('functional PDF smoke passed')
"""


def _run_child(command: Sequence[str], timeout_seconds: float) -> tuple[subprocess.CompletedProcess[str] | None, bool, int]:
    """Run a child interpreter, returning timeout state without raising it."""
    started = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        return completed, False, int((time.monotonic() - started) * 1000)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(command, None, exc.stdout or "", exc.stderr or ""), True, int((time.monotonic() - started) * 1000)
    except OSError as exc:
        return subprocess.CompletedProcess(command, None, "", str(exc)), False, int((time.monotonic() - started) * 1000)


def _distribution_version() -> str | None:
    for distribution in ("PyMuPDF", "pymupdf"):
        try:
            return importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def _supported_version(version: str | None) -> bool:
    """Return whether the reproducibility policy accepts the installed release."""
    if not version:
        return False
    try:
        major, minor, patch = (int(part) for part in version.split(".")[:3])
    except ValueError:
        return False
    return (major, minor, patch) >= (1, 26, 4) and (major, minor) < (1, 27)


def probe_pymupdf(python_executable: str = sys.executable, timeout_seconds: float = 10.0) -> dict:
    """Probe PyMuPDF import and minimal PDF open in isolated subprocesses."""
    discovered = importlib.util.find_spec("fitz") is not None
    version = _distribution_version()
    base = dict(package="pymupdf", module="fitz", version=version, module_discovered=discovered)
    if not discovered:
        result = asdict(NativeProbeResult(**base, status="failed", import_status="module_not_found", functional_status="not_run", return_code=None, signal=None, timed_out=False, stdout="", stderr="", duration_ms=0, reason="module_not_found"))
        result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
        return result
    if not _supported_version(version):
        result = asdict(NativeProbeResult(**base, status="failed", import_status="not_run", functional_status="not_run", return_code=None, signal=None, timed_out=False, stdout="", stderr="", duration_ms=0, reason="unsupported_version"))
        result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
        return result

    import_result, timed_out, duration_ms = _run_child([python_executable, "-c", IMPORT_SMOKE], timeout_seconds)
    if timed_out:
        result = asdict(NativeProbeResult(**base, status="failed", import_status="dependency_probe_timeout", functional_status="not_run", return_code=None, signal=None, timed_out=True, stdout=import_result.stdout or "", stderr=import_result.stderr or "", duration_ms=duration_ms, reason="dependency_probe_timeout"))
        result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
        return result
    if import_result.returncode is None:
        result = asdict(NativeProbeResult(**base, status="failed", import_status="probe_internal_error", functional_status="not_run", return_code=None, signal=None, timed_out=False, stdout=import_result.stdout or "", stderr=import_result.stderr or "", duration_ms=duration_ms, reason="probe_internal_error"))
        result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
        return result
    if import_result.returncode < 0:
        result = asdict(NativeProbeResult(**base, status="failed", import_status="native_dependency_crash", functional_status="not_run", return_code=import_result.returncode, signal=-import_result.returncode, timed_out=False, stdout=import_result.stdout, stderr=import_result.stderr, duration_ms=duration_ms, reason="native_dependency_crash"))
        result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
        return result
    if import_result.returncode != 0:
        result = asdict(NativeProbeResult(**base, status="failed", import_status="import_error", functional_status="not_run", return_code=import_result.returncode, signal=None, timed_out=False, stdout=import_result.stdout, stderr=import_result.stderr, duration_ms=duration_ms, reason="import_error"))
        result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
        return result

    functional_result, timed_out, functional_duration = _run_child([python_executable, "-c", FUNCTIONAL_SMOKE], timeout_seconds)
    total_duration = duration_ms + functional_duration
    if timed_out:
        reason, signal = "dependency_probe_timeout", None
    elif functional_result.returncode is None:
        reason, signal = "probe_internal_error", None
    elif functional_result.returncode < 0:
        reason, signal = "native_dependency_crash", -functional_result.returncode
    elif functional_result.returncode != 0:
        reason, signal = "functional_open_failed", None
    if functional_result.returncode == 0:
        result = asdict(NativeProbeResult(**base, status="passed", import_status="passed", functional_status="passed", return_code=0, signal=None, timed_out=False, stdout=functional_result.stdout, stderr=functional_result.stderr, duration_ms=total_duration))
    else:
        result = asdict(NativeProbeResult(**base, status="failed", import_status="passed", functional_status=reason, return_code=functional_result.returncode, signal=signal, timed_out=timed_out, stdout=functional_result.stdout or "", stderr=functional_result.stderr or "", duration_ms=total_duration, reason=reason))
    result.update(import_smoke_test=result["import_status"], minimal_pdf_open_test=result["functional_status"])
    return result
