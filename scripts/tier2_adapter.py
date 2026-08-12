#!/usr/bin/env python3
"""Quality-gated, isolated Tier-2 candidate adapter orchestration."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from ai_review import fingerprint as native_fingerprint
from tier2_model_manifest import sha256_file, verify_manifest


PROTOCOL_VERSION = "1.0"
AUTO_TRIGGER_CODES = {
    "TABLE_STRUCTURE_UNVERIFIED",
    "OCR_TABLE_GEOMETRY_UNAVAILABLE",
    "OCR_TABLE_IRREGULAR_ROWS",
    "OCR_TABLE_INSUFFICIENT_ROWS",
    "READING_ORDER_UNCERTAIN",
    "TABLE_TEXT_ASSOCIATION_UNCERTAIN",
}
ELIGIBLE_FORMATS = {"pdf", "image"}


def derive_trigger_codes(report: dict) -> list[str]:
    codes = [warning.get("code") for warning in report.get("warnings", [])
             if isinstance(warning, dict)]
    for candidate in (report.get("details") or {}).get("ocr_table_candidates", []):
        codes.extend(candidate.get("reason_codes") or [])
    return list(dict.fromkeys(code for code in codes if code in AUTO_TRIGGER_CODES))


def _schema_errors(value: dict, name: str) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
        schema = json.loads((Path(__file__).parents[1] / "schemas" / name).read_text(
            encoding="utf-8"
        ))
        return [f"{error.json_path}: {error.message}"
                for error in Draft202012Validator(schema).iter_errors(value)]
    except Exception as exc:
        return [str(exc)]


def _safe_artifact(candidate_root: Path, item: dict) -> Path | None:
    candidate = candidate_root / item.get("path", "")
    if candidate.is_symlink():
        return None
    path = candidate.resolve(strict=False)
    try:
        path.relative_to(candidate_root)
    except ValueError:
        return None
    if not path.is_file():
        return None
    if path.stat().st_size != item.get("size_bytes") or sha256_file(path) != item.get("sha256"):
        return None
    return path


def _canonical_digest(bundle: Path) -> str:
    return native_fingerprint(bundle)


def _worker_failure_message(process: subprocess.CompletedProcess) -> str:
    """Prefer the worker's structured error, then retain bounded stderr context."""
    structured = None
    for line in reversed((process.stdout or "").splitlines()):
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and candidate.get("status") == "failed":
            error_type = candidate.get("error_type") or "WorkerError"
            error_message = candidate.get("error_message") or "worker failed"
            structured = f"{error_type}: {error_message}"
            break
    stderr = (process.stderr or "").strip()
    if structured and stderr:
        return (structured + "\nworker stderr tail:\n" + stderr[-1000:])[:2000]
    return (structured or stderr or (process.stdout or "worker result missing"))[-2000:]


def _write_index(tier2_root: Path, index: dict) -> dict:
    tier2_root.mkdir(parents=True, exist_ok=True)
    errors = _schema_errors(index, "tier2-index.schema.json")
    if errors:
        raise ValueError("invalid Tier-2 index: " + "; ".join(errors))
    (tier2_root / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return index


def run_tier2_candidate(input_path: str, bundle_dir: str, report: dict, *,
                        policy: str, model_manifest_path: str | None,
                        timeout_seconds: float = 120.0,
                        document_timeout_seconds: float = 90.0,
                        max_num_pages: int = 100,
                        max_file_size_bytes: int = 20 * 1024 * 1024,
                        worker_command: list[str] | None = None) -> dict:
    input_path = Path(input_path).resolve()
    bundle = Path(bundle_dir).resolve()
    tier2_root = bundle / "tier2"
    trigger_codes = derive_trigger_codes(report)
    source_sha256 = sha256_file(input_path)
    before = _canonical_digest(bundle)
    base = {
        "schema_version": "1.0", "policy": policy, "reason_codes": [],
        "trigger_codes": trigger_codes, "adapter": "docling",
        "source_sha256": source_sha256,
        "native_bundle_fingerprint_before": before,
        "native_bundle_fingerprint_after": before,
        "canonical_mutated": False,
        "selection": "native_retained_pending_manual_review",
        "limits": {
            "subprocess_timeout_seconds": timeout_seconds,
            "document_timeout_seconds": document_timeout_seconds,
            "max_num_pages": max_num_pages,
            "max_file_size_bytes": max_file_size_bytes,
        },
    }
    if report.get("file_type") not in ELIGIBLE_FORMATS:
        base.update(status="not_eligible", reason_codes=["TIER2_FORMAT_NOT_ELIGIBLE"])
        return _write_index(tier2_root, base)
    if policy == "auto" and not trigger_codes:
        base.update(status="not_triggered", reason_codes=["TIER2_QUALITY_GATE_NOT_TRIGGERED"])
        return _write_index(tier2_root, base)
    if not model_manifest_path:
        base.update(status="unavailable", reason_codes=["TIER2_MODEL_MANIFEST_REQUIRED"])
        return _write_index(tier2_root, base)
    manifest_path = Path(model_manifest_path).resolve()
    manifest, errors = verify_manifest(manifest_path)
    if errors:
        base.update(status="unavailable", reason_codes=["TIER2_MODEL_MANIFEST_INVALID"],
                    error_message="; ".join(errors)[:2000])
        return _write_index(tier2_root, base)
    if worker_command is None and importlib.util.find_spec("docling") is None:
        base.update(status="unavailable", reason_codes=["TIER2_ADAPTER_NOT_INSTALLED"],
                    model_manifest_sha256=sha256_file(manifest_path))
        return _write_index(tier2_root, base)

    candidate_root = tier2_root / "candidate"
    candidate_root.mkdir(parents=True, exist_ok=True)
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "input_path": str(input_path),
        "input_format": report["file_type"],
        "source_sha256": source_sha256,
        "output_dir": str(candidate_root),
        "model_manifest_path": str(manifest_path),
        "document_timeout_seconds": document_timeout_seconds,
        "max_num_pages": max_num_pages,
        "max_file_size_bytes": max_file_size_bytes,
        "security": {"remote_services_enabled": False,
                     "external_plugins_enabled": False,
                     "offline_environment_enforced": True},
    }
    request_path = tier2_root / "request.json"
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    command = worker_command or [sys.executable, str(Path(__file__).with_name(
        "tier2_docling_worker.py"))]
    command = [*command, str(request_path)]
    environment = os.environ.copy()
    environment.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                        "DO_NOT_TRACK": "1", "PYTHONUTF8": "1",
                        "PYTHONIOENCODING": "utf-8"})
    started = time.monotonic()
    try:
        process = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_seconds, env=environment,
        )
    except subprocess.TimeoutExpired:
        base.update(status="timed_out", reason_codes=["TIER2_ADAPTER_TIMEOUT"],
                    request_path="tier2/request.json",
                    model_manifest_sha256=sha256_file(manifest_path),
                    duration_ms=round((time.monotonic() - started) * 1000))
        return _finish(tier2_root, bundle, before, base)
    duration_ms = round((time.monotonic() - started) * 1000)
    worker_result_path = candidate_root / "worker-result.json"
    if process.returncode or not worker_result_path.is_file():
        message = _worker_failure_message(process)
        base.update(status="failed", reason_codes=["TIER2_ADAPTER_FAILED"],
                    request_path="tier2/request.json", error_message=message,
                    model_manifest_sha256=sha256_file(manifest_path),
                    duration_ms=duration_ms)
        return _finish(tier2_root, bundle, before, base)
    try:
        worker_result = json.loads(worker_result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        worker_result = {}
        errors = [str(exc)]
    else:
        errors = _schema_errors(worker_result, "tier2-worker-result.schema.json")
    if worker_result.get("source_sha256") != source_sha256:
        errors.append("source hash mismatch")
    if worker_result.get("model", {}).get("manifest_sha256") != sha256_file(manifest_path):
        errors.append("model manifest hash mismatch")
    if any(_safe_artifact(candidate_root, artifact) is None
           for artifact in worker_result.get("artifacts", {}).values()):
        errors.append("candidate artifact validation failed")
    if errors:
        base.update(status="failed", reason_codes=["TIER2_CANDIDATE_VALIDATION_FAILED"],
                    request_path="tier2/request.json", error_message="; ".join(errors)[:2000],
                    model_manifest_sha256=sha256_file(manifest_path),
                    duration_ms=duration_ms)
        return _finish(tier2_root, bundle, before, base)
    base.update(status="candidate_available", reason_codes=["TIER2_CANDIDATE_AVAILABLE"],
                request_path="tier2/request.json",
                candidate_result_path="tier2/candidate/worker-result.json",
                model_manifest_sha256=sha256_file(manifest_path),
                adapter_version=worker_result["adapter"]["version"], duration_ms=duration_ms)
    return _finish(tier2_root, bundle, before, base)


def _finish(tier2_root: Path, bundle: Path, before: str, index: dict) -> dict:
    after = _canonical_digest(bundle)
    if after != before:
        raise RuntimeError("TIER2_NATIVE_CANONICAL_MUTATION_DETECTED")
    index["native_bundle_fingerprint_after"] = after
    return _write_index(tier2_root, index)


def record_internal_failure(input_path: str, bundle_dir: str, report: dict,
                            policy: str, exc: Exception) -> dict:
    """Record an orchestration failure without invalidating native evidence."""
    bundle = Path(bundle_dir).resolve()
    current = _canonical_digest(bundle)
    index = {
        "schema_version": "1.0", "policy": policy, "status": "failed",
        "reason_codes": ["TIER2_INTERNAL_FAILURE"],
        "trigger_codes": derive_trigger_codes(report), "adapter": "docling",
        "source_sha256": sha256_file(Path(input_path).resolve()),
        "native_bundle_fingerprint_before": current,
        "native_bundle_fingerprint_after": current,
        "canonical_mutated": False,
        "selection": "native_retained_pending_manual_review",
        "error_message": str(exc)[:2000],
    }
    return _write_index(bundle / "tier2", index)
