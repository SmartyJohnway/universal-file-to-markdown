#!/usr/bin/env python3
"""Run auditable Tier-2 smoke or hard-corpus qualification."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import router
from tier2_model_manifest import sha256_file, verify_manifest
from validate_bundle import validate_bundle


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_QUALIFICATION_TAGS = {
    "digital_multi_column",
    "scanned_borderless_table",
    "merged_multilevel_header",
    "table_footnote",
    "engineering_drawing",
    "mixed_digital_scanned",
    "low_resolution_image",
    "non_latin_ocr",
    "encrypted_or_password",
    "oversized_or_resource_limit",
}
PACKAGE_NAMES = ("docling", "docling-core", "torch", "transformers", "onnxruntime")


def _schema_errors(value: dict, name: str) -> list[str]:
    from jsonschema import Draft202012Validator

    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    return [f"{error.json_path}: {error.message}"
            for error in Draft202012Validator(schema).iter_errors(value)]


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_corpus(path: Path) -> tuple[dict | None, list[dict], list[str]]:
    """Load a corpus and fail closed on schema, path, or source drift."""
    path = path.resolve()
    try:
        corpus = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [], [f"CORPUS_UNREADABLE: {exc}"]
    errors = [f"CORPUS_SCHEMA_INVALID: {error}"
              for error in _schema_errors(corpus, "tier2-qualification-corpus.schema.json")]
    root = path.parent
    resolved = []
    seen = set()
    for item in corpus.get("documents", []):
        case_id = item.get("case_id")
        if case_id in seen:
            errors.append(f"CORPUS_DUPLICATE_CASE_ID: {case_id}")
        seen.add(case_id)
        relative = item.get("source_path")
        if not isinstance(relative, str) or Path(relative).is_absolute():
            errors.append(f"CORPUS_SOURCE_PATH_INVALID: {case_id}")
            continue
        source = (root / relative).resolve(strict=False)
        try:
            source.relative_to(root)
        except ValueError:
            errors.append(f"CORPUS_SOURCE_PATH_ESCAPE: {case_id}")
            continue
        if source.is_symlink() or not source.is_file():
            errors.append(f"CORPUS_SOURCE_MISSING: {case_id}")
            continue
        if _digest(source) != item.get("sha256"):
            errors.append(f"CORPUS_SOURCE_HASH_MISMATCH: {case_id}")
            continue
        resolved.append({**item, "resolved_source": source})
    return corpus, resolved, errors


def _versions() -> dict:
    versions = {}
    for name in PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _candidate_metrics(bundle: Path, index: dict) -> dict:
    metrics = {"candidate_text_chars": 0, "candidate_tables": 0,
               "candidate_artifact_hashes": {}, "candidate_markdown": ""}
    if index.get("status") != "candidate_available":
        return metrics
    result_path = bundle / index["candidate_result_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    candidate_root = result_path.parent
    markdown_item = result["artifacts"]["markdown"]
    document_item = result["artifacts"]["docling_document"]
    markdown = (candidate_root / markdown_item["path"]).read_text(encoding="utf-8")
    document = json.loads((candidate_root / document_item["path"]).read_text(encoding="utf-8"))
    tables = document.get("tables", [])
    metrics.update(
        candidate_text_chars=len(markdown),
        candidate_tables=len(tables) if isinstance(tables, list) else 0,
        candidate_artifact_hashes={name: artifact["sha256"]
                                   for name, artifact in result["artifacts"].items()},
        candidate_markdown=markdown,
    )
    return metrics


def _expectation_errors(actual: dict, expected: dict) -> list[str]:
    errors = []
    if actual["tier2_status"] not in expected.get("tier2_statuses", []):
        errors.append("TIER2_STATUS_UNEXPECTED")
    if actual["candidate_text_chars"] < expected.get("min_candidate_text_chars", 0):
        errors.append("CANDIDATE_TEXT_COVERAGE_BELOW_MINIMUM")
    if actual["candidate_tables"] < expected.get("min_candidate_tables", 0):
        errors.append("CANDIDATE_TABLE_COUNT_BELOW_MINIMUM")
    for fragment in expected.get("required_markdown_fragments", []):
        if fragment not in actual["candidate_markdown"]:
            errors.append(f"CANDIDATE_MARKDOWN_FRAGMENT_MISSING: {fragment}")
    for code in expected.get("required_reason_codes", []):
        if code not in actual.get("tier2_reason_codes", []):
            errors.append(f"TIER2_REASON_CODE_MISSING: {code}")
    for fragment in expected.get("required_error_fragments", []):
        if fragment not in (actual.get("tier2_error_message") or ""):
            errors.append(f"TIER2_ERROR_FRAGMENT_MISSING: {fragment}")
    maximum = expected.get("max_duration_seconds")
    if maximum is not None and actual["wall_duration_seconds"] > maximum:
        errors.append("TIER2_DURATION_ABOVE_MAXIMUM")
    return errors


def _runs_are_deterministic(case_runs: list[dict], expected_runs: int) -> bool:
    statuses = [run["tier2_status"] for run in case_runs]
    native_hashes = [run["native_fingerprint"] for run in case_runs
                     if run.get("native_fingerprint")]
    if len(case_runs) != expected_runs or not statuses or len(set(statuses)) != 1:
        return False
    if statuses[0] != "candidate_available":
        return len(set(native_hashes)) <= 1
    candidate_hashes = [run["candidate_artifact_hashes"] for run in case_runs]
    return (len({json.dumps(value, sort_keys=True) for value in candidate_hashes}) == 1
            and len(set(native_hashes)) <= 1)


def execute_case(item: dict, output: Path, model_manifest: Path, *, runs: int,
                 timeout_seconds: float, document_timeout_seconds: float,
                 max_num_pages: int, max_file_size_bytes: int) -> dict:
    case_runs = []
    for run_index in range(1, runs + 1):
        bundle = output / "bundles" / item["case_id"] / f"run-{run_index:02d}"
        started = time.monotonic()
        report = router.convert(
            str(item["resolved_source"]), str(bundle), tier2_policy="force",
            tier2_model_manifest=str(model_manifest),
            tier2_timeout_seconds=timeout_seconds,
            tier2_document_timeout_seconds=document_timeout_seconds,
            tier2_max_num_pages=max_num_pages,
            tier2_max_file_size_bytes=max_file_size_bytes,
        )
        wall = round(time.monotonic() - started, 3)
        tier2 = report.get("tier2") or {}
        tier2_status = tier2.get("status") or "native_failed"
        validation = (validate_bundle(str(bundle))
                      if report.get("status") != "failed" else {"status": "not_available", "errors": []})
        metrics = _candidate_metrics(bundle, tier2)
        actual = {
            "run": run_index,
            "status": "failed",
            "native_status": report.get("status"),
            "bundle_validation_status": validation["status"],
            "bundle_validation_errors": validation.get("errors", []),
            "tier2_status": tier2_status,
            "tier2_reason_codes": tier2.get("reason_codes", []),
            "tier2_error_message": tier2.get("error_message"),
            "native_fingerprint": tier2.get("native_bundle_fingerprint_after"),
            "canonical_mutated": tier2.get("canonical_mutated"),
            "wall_duration_seconds": wall,
            "adapter_duration_ms": tier2.get("duration_ms"),
            **metrics,
        }
        errors = _expectation_errors(actual, item["expected"])
        if report.get("status") != "failed" and validation["status"] != "passed":
            errors.append("BUNDLE_VALIDATION_FAILED")
        if tier2_status == "candidate_available" and tier2.get("canonical_mutated") is not False:
            errors.append("NATIVE_CANONICAL_NOT_PRESERVED")
        actual["errors"] = errors
        actual["status"] = "passed" if not errors else "failed"
        actual.pop("candidate_markdown", None)
        case_runs.append(actual)

    deterministic = _runs_are_deterministic(case_runs, runs)
    case_errors = []
    if runs > 1 and not deterministic:
        case_errors.append("TIER2_RERUN_NOT_DETERMINISTIC")
    if any(run["status"] != "passed" for run in case_runs):
        case_errors.append("ONE_OR_MORE_RUNS_FAILED")
    durations = [run["wall_duration_seconds"] for run in case_runs]
    return {
        "case_id": item["case_id"], "format": item["format"],
        "source_sha256": item["sha256"], "source_url": item.get("source_url"),
        "license": item.get("license"), "tags": item["tags"],
        "status": "passed" if not case_errors else "failed", "errors": case_errors,
        "deterministic": deterministic, "runs": case_runs,
        "duration_seconds": {"min": min(durations), "median": statistics.median(durations),
                             "max": max(durations)},
    }


def qualify(corpus_path: Path, model_manifest: Path, output: Path, *, mode: str,
            runs: int, timeout_seconds: float, document_timeout_seconds: float,
            max_num_pages: int, max_file_size_bytes: int,
            executor=execute_case) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    corpus, documents, corpus_errors = load_corpus(corpus_path)
    model, model_errors = verify_manifest(model_manifest.resolve())
    scope_errors = []
    tags = {tag for item in documents for tag in item.get("tags", [])}
    if mode == "qualification":
        if len(documents) < 10:
            scope_errors.append("QUALIFICATION_REQUIRES_AT_LEAST_10_DOCUMENTS")
        missing = sorted(REQUIRED_QUALIFICATION_TAGS - tags)
        scope_errors.extend(f"QUALIFICATION_TAG_MISSING: {tag}" for tag in missing)
        if runs < 2:
            scope_errors.append("QUALIFICATION_REQUIRES_AT_LEAST_TWO_RUNS")
        for item in documents:
            if not str(item.get("source_url", "")).startswith("https://") or not item.get("license"):
                scope_errors.append(f"QUALIFICATION_PROVENANCE_INCOMPLETE: {item['case_id']}")

    cases = []
    if not corpus_errors and not model_errors:
        for item in documents:
            cases.append(executor(
                item, output, model_manifest.resolve(), runs=runs,
                timeout_seconds=timeout_seconds,
                document_timeout_seconds=document_timeout_seconds,
                max_num_pages=max_num_pages,
                max_file_size_bytes=max_file_size_bytes,
            ))
    passed = sum(case["status"] == "passed" for case in cases)
    case_runs = [run for case in cases for run in case.get("runs", [])]
    gate_passed = (mode == "qualification" and not corpus_errors and not model_errors
                   and not scope_errors and passed == len(cases))
    run_passed = (not corpus_errors and not model_errors and passed == len(documents))
    status = "passed" if run_passed and (mode == "smoke" or gate_passed) else "failed"
    blockers = list(dict.fromkeys([
        *corpus_errors, *model_errors, *scope_errors,
        "MULTI_PLATFORM_EVIDENCE_REQUIRED",
        "PEAK_MEMORY_AND_RESOURCE_ISOLATION_EVIDENCE_REQUIRED",
        "HERMES_CONSUMER_EVIDENCE_REQUIRED",
    ]))
    report = {
        "schema_version": "1.0", "mode": mode, "status": status,
        "qualification_gate_status": ("passed" if gate_passed else
                                      "failed" if mode == "qualification" else "not_evaluated"),
        "production_qualified": False, "production_blockers": blockers,
        "corpus": {"corpus_id": (corpus or {}).get("corpus_id"),
                   "manifest_sha256": _digest(corpus_path.resolve()) if corpus else None,
                   "errors": corpus_errors, "covered_tags": sorted(tags)},
        "environment": {"platform": platform.platform(), "python": sys.version.split()[0],
                        "executable": sys.executable, "packages": _versions()},
        "model": {"manifest_path": str(model_manifest.resolve()),
                  "manifest_sha256": sha256_file(model_manifest.resolve()) if model_manifest.is_file() else None,
                  "model_id": (model or {}).get("model_id"),
                  "model_version": (model or {}).get("model_version"), "errors": model_errors},
        "limits": {"subprocess_timeout_seconds": timeout_seconds,
                   "document_timeout_seconds": document_timeout_seconds,
                   "max_num_pages": max_num_pages,
                   "max_file_size_bytes": max_file_size_bytes},
        "summary": {"case_count": len(cases), "passed": passed,
                    "failed": len(cases) - passed, "run_count": len(case_runs),
                    "candidate_available_runs": sum(run.get("tier2_status") == "candidate_available"
                                                    for run in case_runs),
                    "deterministic_cases": sum(case.get("deterministic") is True for case in cases)},
        "cases": cases,
    }
    schema_errors = _schema_errors(report, "tier2-qualification-report.schema.json")
    if schema_errors:
        raise RuntimeError("invalid Tier-2 qualification report: " + "; ".join(schema_errors))
    (output / "tier2-qualification-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--model-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "qualification"), default="smoke")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--document-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--max-num-pages", type=int, default=100)
    parser.add_argument("--max-file-size-bytes", type=int, default=20 * 1024 * 1024)
    args = parser.parse_args()
    if (args.runs < 1 or args.timeout_seconds <= 0 or args.document_timeout_seconds <= 0
            or args.max_num_pages < 1 or args.max_file_size_bytes < 1):
        parser.error("runs and all timeout/limit values must be greater than zero")
    report = qualify(
        args.corpus, args.model_manifest, args.output, mode=args.mode, runs=args.runs,
        timeout_seconds=args.timeout_seconds,
        document_timeout_seconds=args.document_timeout_seconds,
        max_num_pages=args.max_num_pages, max_file_size_bytes=args.max_file_size_bytes,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
