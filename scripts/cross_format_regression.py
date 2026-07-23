"""Reproducible, contract-focused helpers for cross-format regressions.

The normalized model intentionally excludes execution evidence (timestamps,
absolute directories and durations), but retains warning codes, locators and
OCR confidence values.  OCR confidence comparisons use ``1e-6`` absolute
tolerance; they are never discarded wholesale.
"""
import hashlib
import json
import os
import re
from pathlib import Path

VOLATILE_KEYS = {"converted_at", "generated_at", "started_at", "finished_at",
                 "duration", "duration_ms", "output_dir", "output_path", "hostname"}
OCR_TOLERANCE = {"field": "confidence", "comparison": "numeric_tolerance", "absolute_tolerance": 0.000001}

def _text(value): return value.replace("\r\n", "\n").replace("\r", "\n") if isinstance(value, str) else value
def _normal(value, bundle=None):
    if isinstance(value, dict):
        return {key: _normal(val, bundle) for key, val in sorted(value.items()) if key not in VOLATILE_KEYS}
    if isinstance(value, list): return [_normal(item, bundle) for item in value]
    if isinstance(value, str):
        value = _text(value)
        if bundle and os.path.isabs(value):
            try: return Path(value).resolve().relative_to(bundle.resolve()).as_posix()
            except ValueError: return "<absolute-path>" + Path(value).name
        return value.replace("\\", "/")
    return value

def _load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

def normalize_bundle(bundle):
    """Return a non-destructive stable model; canonical list order is retained."""
    bundle = Path(bundle)
    chunks = [_normal(json.loads(line), bundle) for line in (bundle / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()] if (bundle / "chunks.jsonl").exists() else []
    tables = []
    for path in sorted((bundle / "tables").glob("*.json")) if (bundle / "tables").exists() else []:
        if path.name != "index.json": tables.append(_normal(_load_json(path, {}), bundle))
    assets = []
    for path in sorted((bundle / "assets").rglob("*")) if (bundle / "assets").exists() else []:
        if path.is_file(): assets.append({"path": path.relative_to(bundle).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    report = _normal(_load_json(bundle / "conversion-report.json", {}), bundle)
    manifest = _normal(_load_json(bundle / "manifest.json", {}), bundle)
    return {"normalization_schema_version":"1.0", "document_markdown": _text((bundle / "document.md").read_text(encoding="utf-8")) if (bundle / "document.md").exists() else "",
            "document": _normal(_load_json(bundle / "document.json", {}), bundle), "chunks": chunks, "tables": tables, "assets": assets,
            "manifest_contract": {k: manifest.get(k) for k in ("status", "file_type", "source_sha256") if k in manifest},
            "report_contract": {k: report.get(k) for k in ("status", "engine", "warnings", "bundle_validation", "bundle_validation_status", "ai_review_status", "readable_projection_status") if k in report},
            "ai_artifacts": {name: _normal(_load_json(bundle / name, {}), bundle) for name in ("ai-review-request.json", "ai-review.json") if (bundle / name).exists()},
            "readable_projection": _text((bundle / "document-readable.md").read_text(encoding="utf-8")) if (bundle / "document-readable.md").exists() else None}

def stable_bytes(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
def fingerprint(normalized):
    artifacts = {key: hashlib.sha256(stable_bytes(value)).hexdigest() for key, value in normalized.items() if key not in {"normalization_schema_version"}}
    return {"fingerprint_schema_version":"1.0", "bundle_fingerprint":hashlib.sha256(stable_bytes(normalized)).hexdigest(), "artifact_fingerprints":artifacts}

def semantically_equal(before, after, path=""):
    """Compare canonical models, allowing only bounded OCR confidence drift."""
    if isinstance(before, dict) and isinstance(after, dict):
        return before.keys()==after.keys() and all(semantically_equal(before[k],after[k],path+'.'+k) for k in before)
    if isinstance(before, list) and isinstance(after, list):
        return len(before)==len(after) and all(semantically_equal(a,b,path+'[]') for a,b in zip(before,after))
    if path.endswith('.confidence') and isinstance(before,(int,float)) and isinstance(after,(int,float)):
        return abs(before-after) <= OCR_TOLERANCE['absolute_tolerance']
    return before == after

def diff_models(before, after, excerpt_limit=240):
    """Bounded, human-oriented differences rather than an opaque hash mismatch."""
    changes=[]
    def add(kind, path, old=None, new=None):
        changes.append({"category":kind,"path":path,"before":str(old)[:excerpt_limit],"after":str(new)[:excerpt_limit]})
    for key, category in (("document", "content_changed"), ("tables", "table_cell_changed"), ("chunks", "chunk_boundary_changed"), ("assets", "asset_hash_changed"), ("ai_artifacts", "AI artifact changed")):
        if before.get(key) != after.get(key): add(category, key, before.get(key), after.get(key))
    old_report,new_report=before.get('report_contract',{}),after.get('report_contract',{})
    if old_report.get('status') != new_report.get('status'): add('status_changed','report_contract.status',old_report.get('status'),new_report.get('status'))
    old_codes={w.get('code') for w in old_report.get('warnings',[]) if isinstance(w,dict)}; new_codes={w.get('code') for w in new_report.get('warnings',[]) if isinstance(w,dict)}
    for code in sorted(new_codes-old_codes): add('warning_added','warnings',None,code)
    for code in sorted(old_codes-new_codes): add('warning_removed','warnings',code,None)
    if before.get("document_markdown") != after.get("document_markdown"): add("content_changed", "document.md", before.get("document_markdown"), after.get("document_markdown"))
    return changes

def write_diff(before, after, output, case_id):
    changes=diff_models(before, after); output=Path(output); output.mkdir(parents=True, exist_ok=True)
    (output / f"{case_id}.json").write_text(json.dumps({"case_id":case_id,"changes":changes}, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    (output / f"{case_id}.md").write_text("# Regression diff: %s\n\n%s\n" % (case_id, "\n".join("- **%s** `%s`: `%s` → `%s`" % (c["category"],c["path"],c["before"],c["after"]) for c in changes) or "No semantic differences."), encoding="utf-8")
    return changes
