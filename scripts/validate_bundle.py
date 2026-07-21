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
    root_id = document.get("root_element_id")
    root = by_id.get(root_id)
    if root is None:
        errors.append("root_element_id does not reference an existing element")
    else:
        if root.get("type") != "document":
            errors.append("root element type must be document")
        if root.get("parent_id") is not None:
            errors.append("root element parent_id must be null")
    if document.get("element_count") != len(elements):
        errors.append("element_count does not match elements length")
    if document.get("content_element_count") != max(0, len(elements) - 1):
        errors.append("content_element_count does not match non-root element count")
    for element in elements:
        parent_id = element.get("parent_id")
        if parent_id is not None and parent_id not in by_id:
            errors.append(f"missing parent {parent_id} for element {element.get('id')}")
        elif (parent_id is not None
              and element.get("id") not in (by_id[parent_id].get("children") or [])):
            errors.append(f"parent {parent_id} does not reference child {element.get('id')}")
        if element.get("children") != element.get("child_ids"):
            errors.append(f"children/child_ids mismatch for {element.get('id')}")
        for child_id in element.get("children") or []:
            if child_id not in by_id or by_id[child_id].get("parent_id") != element.get("id"):
                errors.append(f"invalid child reference {child_id} from {element.get('id')}")
        if element.get("type") == "image" and element.get("asset"):
            if not os.path.isfile(os.path.join(bundle_dir, "assets", element["asset"])):
                errors.append(f"missing image asset: {element['asset']}")

    if root is not None:
        reachable_from_root, pending = set(), [root_id]
        while pending:
            element_id = pending.pop()
            if element_id in reachable_from_root or element_id not in by_id:
                continue
            reachable_from_root.add(element_id)
            pending.extend(by_id[element_id].get("children") or [])
        disconnected = set(by_id) - reachable_from_root
        if disconnected:
            errors.append(f"elements are not reachable from root: {sorted(disconnected)}")

        cycle_nodes = set()
        resolved = {root_id}
        for element_id in by_id:
            path, positions = [], {}
            current_id = element_id
            while current_id in by_id and current_id not in resolved:
                if current_id in positions:
                    cycle_nodes.update(path[positions[current_id]:])
                    break
                positions[current_id] = len(path)
                path.append(current_id)
                current_id = by_id[current_id].get("parent_id")
            resolved.update(path)
        if cycle_nodes:
            errors.append(f"hierarchy cycle detected at elements: {sorted(cycle_nodes)}")

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
            if chunk.get("char_count") != len(chunk.get("text", "")):
                errors.append(f"chunk char_count mismatch: {chunk.get('chunk_id')}")
            if len(chunk.get("text", "")) > HARD_MAX_CHUNK_CHARS:
                errors.append(f"chunk exceeds hard limit: {chunk.get('chunk_id')}")
            for element_id in chunk.get("element_ids", []):
                if element_id not in by_id:
                    errors.append(f"chunk references missing element: {element_id}")

    chunk_ids = [chunk.get("chunk_id") for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        errors.append("chunk IDs are not unique")
    chunk_indexes = [chunk.get("chunk_index") for chunk in chunks]
    if (len(chunk_indexes) != len(set(chunk_indexes))
            or sorted(index for index in chunk_indexes if isinstance(index, int))
            != list(range(1, len(chunks) + 1))):
        errors.append("chunk_index values must be unique and contiguous from 1")
    for chunk in chunks:
        part_index, part_count = chunk.get("part_index"), chunk.get("part_count")
        if (not isinstance(part_index, int) or not isinstance(part_count, int)
                or part_index < 1 or part_count < 1 or part_index > part_count):
            errors.append(f"invalid chunk part index: {chunk.get('chunk_id')}")

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
                table = _load_json(table_json)
                _schema_validate(table, "table.schema.json", errors)
                _validate_table_semantics(table, errors)
    if table_elements - table_ids:
        errors.append(f"table elements reference missing assets: {sorted(table_elements - table_ids)}")

    if not re.fullmatch(r"[0-9a-f]{64}", manifest.get("source_sha256", "")):
        errors.append("manifest source_sha256 is not a SHA-256 hex digest")
    return {"status": "passed" if not errors else "failed", "errors": errors,
            "warnings": warnings, "counts": {"elements": len(elements),
            "chunks": len(chunks), "tables": len(table_ids)}}


def _validate_table_semantics(table: dict, errors: list) -> None:
    table_id = table.get("id")
    dimensions = table.get("dimensions") or {}
    rows, columns = dimensions.get("rows"), dimensions.get("columns")
    grid = table.get("grid") or []
    if not isinstance(rows, int) or not isinstance(columns, int):
        return
    if rows != len(grid):
        errors.append(f"table {table_id} row dimension does not match grid")
    if any(not isinstance(row, list) or len(row) != columns for row in grid):
        errors.append(f"table {table_id} column dimension does not match grid")
    for cell in table.get("cells") or []:
        row, column = cell.get("row"), cell.get("column")
        rowspan, colspan = cell.get("rowspan"), cell.get("colspan")
        if not all(isinstance(value, int) for value in (row, column, rowspan, colspan)):
            continue
        if (row < 0 or column < 0 or rowspan < 1 or colspan < 1
                or row + rowspan > rows or column + colspan > columns):
            errors.append(f"table {table_id} cell is outside declared dimensions")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a converted output bundle")
    parser.add_argument("bundle", help="Output bundle directory")
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "passed" else 1)
