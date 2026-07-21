#!/usr/bin/env python3
"""Validate a v1.6 output bundle and its cross-file references."""

import argparse
import json
import os
import re
import sys

HARD_MAX_CHUNK_CHARS = 2000


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _schema_validate(instance, schema_name, errors):
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        errors.append("jsonschema dependency is not installed")
        return
    schema_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schemas")
    schema = _load_json(os.path.join(schema_dir, schema_name))
    if schema_name == "document.schema.json":
        schema["properties"]["elements"]["items"] = _load_json(
            os.path.join(schema_dir, "element.schema.json"))
    for error in Draft202012Validator(schema).iter_errors(instance):
        errors.append(f"{schema_name}: {error.json_path}: {error.message}")


def validate_bundle(bundle_dir: str) -> dict:
    errors, warnings = [], []
    bundle_dir = os.path.abspath(bundle_dir)
    required = ("document.md", "document.json", "chunks.jsonl", "manifest.json",
                "conversion-report.json")
    for name in required:
        if not os.path.isfile(os.path.join(bundle_dir, name)):
            errors.append(f"missing required file: {name}")
    if errors:
        return {"status": "failed", "errors": errors, "warnings": warnings}

    manifest = _load_json(os.path.join(bundle_dir, "manifest.json"))
    document = _load_json(os.path.join(bundle_dir, "document.json"))
    _schema_validate(document, "document.schema.json", errors)
    if document.get("source_sha256") != manifest.get("source_sha256"):
        errors.append("document.json source_sha256 does not match manifest.json")

    elements = document.get("elements", [])
    ids = [element.get("id") for element in elements]
    if len(ids) != len(set(ids)):
        errors.append("element IDs are not unique")
    by_id = {element.get("id"): element for element in elements}
    for element in elements:
        parent_id = element.get("parent_id")
        if parent_id is not None and parent_id not in by_id:
            errors.append(f"missing parent {parent_id} for element {element.get('id')}")
        if element.get("children") != element.get("child_ids"):
            errors.append(f"children/child_ids mismatch for {element.get('id')}")
        for child_id in element.get("children", []):
            if child_id not in by_id or by_id[child_id].get("parent_id") != element.get("id"):
                errors.append(f"invalid child reference {child_id} from {element.get('id')}")
        if element.get("type") == "image" and element.get("asset"):
            if not os.path.isfile(os.path.join(bundle_dir, "assets", element["asset"])):
                errors.append(f"missing image asset: {element['asset']}")

    chunks = []
    with open(os.path.join(bundle_dir, "chunks.jsonl"), encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"chunks.jsonl line {line_number}: {exc}")
                continue
            chunks.append(chunk)
            _schema_validate(chunk, "chunk.schema.json", errors)
            if len(chunk.get("text", "")) > HARD_MAX_CHUNK_CHARS:
                errors.append(f"chunk exceeds hard limit: {chunk.get('chunk_id')}")
            for element_id in chunk.get("element_ids", []):
                if element_id not in by_id:
                    errors.append(f"chunk references missing element: {element_id}")

    table_ids = set()
    table_elements = {element.get("table_id") for element in elements if element.get("table_id")}
    index_path = os.path.join(bundle_dir, "tables", "index.json")
    if os.path.isfile(index_path):
        for entry in _load_json(index_path):
            table_id = entry.get("id")
            if table_id in table_ids:
                errors.append(f"duplicate table ID in index: {table_id}")
            table_ids.add(table_id)
            for asset in (entry.get("assets") or {}).values():
                if not os.path.isfile(os.path.join(bundle_dir, "tables", asset)):
                    errors.append(f"missing table asset: {asset}")
            table_json = os.path.join(bundle_dir, "tables", f"{table_id}.json")
            if os.path.isfile(table_json):
                _schema_validate(_load_json(table_json), "table.schema.json", errors)
    if table_elements - table_ids:
        errors.append(f"table elements reference missing assets: {sorted(table_elements - table_ids)}")

    if not re.fullmatch(r"[0-9a-f]{64}", manifest.get("source_sha256", "")):
        errors.append("manifest source_sha256 is not a SHA-256 hex digest")
    return {"status": "passed" if not errors else "failed", "errors": errors,
            "warnings": warnings, "counts": {"elements": len(elements),
            "chunks": len(chunks), "tables": len(table_ids)}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a converted output bundle")
    parser.add_argument("bundle", help="Output bundle directory")
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "passed" else 1)
