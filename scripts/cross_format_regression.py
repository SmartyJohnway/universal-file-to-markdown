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

def _is_ocr_record(value):
    engine=str(value.get("engine", "")).lower()
    return any(token in engine for token in ("rapidocr", "tesseract", "ocr")) or value.get("confidence_kind") == "ocr" or value.get("type") in {"ocr_region", "ocr_table"}

def semantically_equal(before, after, path=""):
    """Compare models; tolerance is restricted to explicitly OCR-derived records."""
    if isinstance(before, dict) and isinstance(after, dict):
        if before.keys() != after.keys(): return False
        for key in before:
            if key == "confidence" and _is_ocr_record(before) and _is_ocr_record(after) and isinstance(before[key],(int,float)) and isinstance(after[key],(int,float)):
                if abs(before[key]-after[key]) > OCR_TOLERANCE['absolute_tolerance']: return False
            elif not semantically_equal(before[key],after[key],path+'.'+key): return False
        return True
    if isinstance(before, list) and isinstance(after, list):
        return len(before)==len(after) and all(semantically_equal(a,b,path+'[]') for a,b in zip(before,after))
    return before == after

def diff_models(before, after, excerpt_limit=240):
    """Bounded, human-oriented differences rather than an opaque hash mismatch."""
    changes=[]
    def add(kind, path, old=None, new=None):
        changes.append({"category":kind,"path":path,"before":str(old)[:excerpt_limit],"after":str(new)[:excerpt_limit]})
    old_elements={item.get('id'):item for item in before.get('document',{}).get('elements',[]) if item.get('id')}
    new_elements={item.get('id'):item for item in after.get('document',{}).get('elements',[]) if item.get('id')}
    for ident in sorted(new_elements.keys()-old_elements.keys()): add('element_added','document.elements.'+ident,None,new_elements[ident])
    for ident in sorted(old_elements.keys()-new_elements.keys()): add('element_removed','document.elements.'+ident,old_elements[ident],None)
    for ident in sorted(old_elements.keys()&new_elements.keys()):
        old,new=old_elements[ident],new_elements[ident]
        if old.get('type') != new.get('type'): add('element_type_changed','document.elements.'+ident+'.type',old.get('type'),new.get('type'))
        if old.get('source_locator') != new.get('source_locator'): add('locator_changed','document.elements.'+ident+'.source_locator',old.get('source_locator'),new.get('source_locator'))
        if old.get('heading_path') != new.get('heading_path'): add('heading_path_changed','document.elements.'+ident+'.heading_path',old.get('heading_path'),new.get('heading_path'))
        if old.get('content') != new.get('content'): add('content_changed','document.elements.'+ident+'.content',old.get('content'),new.get('content'))
    old_tables={item.get('id'):item for item in before.get('tables',[]) if item.get('id')}; new_tables={item.get('id'):item for item in after.get('tables',[]) if item.get('id')}
    for ident in sorted(new_tables.keys()-old_tables.keys()): add('table_added','tables.'+ident,None,new_tables[ident])
    for ident in sorted(old_tables.keys()-new_tables.keys()): add('table_removed','tables.'+ident,old_tables[ident],None)
    table_specific=False
    for ident in sorted(old_tables.keys()&new_tables.keys()):
        old,new=old_tables[ident],new_tables[ident]
        if old.get('dimensions') != new.get('dimensions'):
            add('table_dimensions_changed','tables.'+ident+'.dimensions',old.get('dimensions'),new.get('dimensions')); table_specific=True
        def merges(table): return sorted((cell.get('row'),cell.get('column'),cell.get('rowspan',1),cell.get('colspan',1)) for cell in table.get('cells',[]) if cell.get('rowspan',1)>1 or cell.get('colspan',1)>1)
        if merges(old) != merges(new): add('merge_changed','tables.'+ident+'.cells',merges(old),merges(new)); table_specific=True
        if old.get('cells') != new.get('cells') and not table_specific: add('table_cell_changed','tables.'+ident+'.cells',old.get('cells'),new.get('cells'))
    for key, category in (("document", "content_changed"), ("chunks", "chunk_boundary_changed"), ("assets", "asset_hash_changed"), ("ai_artifacts", "AI artifact changed")):
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
