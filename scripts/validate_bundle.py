#!/usr/bin/env python3
"""Validate a v1.6 output bundle and its cross-file references."""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from markdown_refs import parse_markdown_image_references

HARD_MAX_CHUNK_CHARS = 2000
LOCATOR_PRECISIONS = {"exact", "range", "page_only", "derived", "unknown"}
LOCATOR_FORMATS = {"xlsx", "pptx", "pdf", "docx", "eml", "csv", "json", "html", "pandoc", "image", "text", "unknown"}


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

    _validate_markdown_image_targets(bundle_dir, errors)

    manifest = _load_json(os.path.join(bundle_dir, "manifest.json"))
    document = _load_json(os.path.join(bundle_dir, "document.json"))
    _schema_validate(document, "document.schema.json", errors)
    if document.get("source_sha256") != manifest.get("source_sha256"):
        errors.append("document.json source_sha256 does not match manifest.json")

    elements = document.get("elements", [])
    _validate_canonical_asset_targets(bundle_dir, elements, errors)
    for element in elements:
        _validate_provenance(element, errors, "ELEMENT")
    ids = [element.get("id") for element in elements]
    if len(ids) != len(set(ids)):
        errors.append("element IDs are not unique")
    by_id = {element.get("id"): element for element in elements}
    _validate_element_layout_and_associations(elements, by_id, errors)
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
            element_ids = chunk.get("element_ids", [])
            if len(element_ids) != len(set(element_ids)):
                errors.append("CHUNK_ELEMENT_REFERENCE_MISSING: duplicate element_ids")
            for element_id in element_ids:
                if element_id not in by_id:
                    errors.append(f"CHUNK_ELEMENT_REFERENCE_MISSING: missing element {element_id}")
            _validate_provenance(chunk, errors, "CHUNK")
            _validate_chunk_consumer_contract(chunk, by_id, errors)

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
    html_tables = []
    table_elements = {element.get("table_id") for element in elements if element.get("table_id")}
    index_path = os.path.join(bundle_dir, "tables", "index.json")
    if os.path.isfile(index_path):
        try:
            index_entries = _load_json(index_path)
        except (OSError, json.JSONDecodeError):
            errors.append("TABLE_INDEX_MALFORMED")
            index_entries = []
        if not isinstance(index_entries, list):
            errors.append("TABLE_INDEX_MALFORMED")
            index_entries = []
        for entry in index_entries:
            if not isinstance(entry, dict):
                errors.append("TABLE_INDEX_MALFORMED")
                continue
            table_id = entry.get("id")
            if table_id in table_ids:
                errors.append(f"duplicate table ID in index: {table_id}")
            table_ids.add(table_id)
            assets = entry.get("assets") or {}
            if not isinstance(assets, dict):
                errors.append("TABLE_INDEX_MALFORMED")
                assets = {}
            table_root = Path(bundle_dir, "tables").resolve()
            for asset in assets.values():
                target = (table_root / asset).resolve(strict=False) if isinstance(asset, str) else None
                try:
                    contained = target is not None and target.relative_to(table_root)
                except ValueError:
                    contained = None
                if contained is None or target is None or not target.is_file():
                    errors.append(f"missing table asset: {asset}")
            table_json = os.path.join(bundle_dir, "tables", f"{table_id}.json")
            if os.path.isfile(table_json):
                table = _load_json(table_json)
                _schema_validate(table, "table.schema.json", errors)
                _validate_table_semantics(table, errors)
                if table.get("source_format") == "html":
                    html_tables.append(table)
    for chunk in chunks:
        ids = chunk.get("table_ids", [])
        if len(ids) != len(set(ids)):
            errors.append("CHUNK_TABLE_REFERENCE_MISSING: duplicate table_ids")
        for table_id in ids:
            if table_id not in table_ids:
                errors.append(f"CHUNK_TABLE_REFERENCE_MISSING: {table_id}")

    if table_elements - table_ids:
        errors.append(f"table elements reference missing assets: {sorted(table_elements - table_ids)}")

    report = _load_json(os.path.join(bundle_dir, "conversion-report.json"))
    _validate_html_metrics(report, html_tables, errors)
    _validate_ocr_table_metrics(report, table_ids, bundle_dir, errors)

    if not re.fullmatch(r"[0-9a-f]{64}", manifest.get("source_sha256", "")):
        errors.append("manifest source_sha256 is not a SHA-256 hex digest")
    return {"status": "passed" if not errors else "failed", "errors": errors,
            "warnings": warnings, "counts": {"elements": len(elements),
            "chunks": len(chunks), "tables": len(table_ids)}}


def _validate_provenance(record: dict, errors: list, subject: str) -> None:
    """Apply the same precision/evidence contract to elements and chunks."""
    precision = record.get("locator_precision")
    if precision is None:
        # Legacy v1.6.0 records may omit the optional extension.
        return
    if precision not in LOCATOR_PRECISIONS:
        errors.append("LOCATOR_PRECISION_INVALID")
        return
    single, many = record.get("source_locator"), record.get("source_locators")
    if single is not None and many is not None:
        errors.append("CHUNK_LOCATOR_CONFLICT" if subject == "CHUNK" else "ELEMENT_LOCATOR_CONFLICT")
        return
    locators = [single] if isinstance(single, dict) else (many or [])
    if many is not None and (not isinstance(many, list) or not many):
        errors.append("CHUNK_LOCATOR_CONFLICT" if subject == "CHUNK" else "ELEMENT_LOCATOR_CONFLICT")
    if precision == "unknown":
        return
    for locator in locators:
        _validate_source_locator(locator, errors)
    if not locators:
        errors.append("LOCATOR_PRECISION_MISSING")
        return
    if precision == "range" and len(locators) > 1:
        return
    locator = locators[0]
    fmt = locator.get("format")
    exact_evidence = {
        "xlsx": bool(locator.get("sheet_name") and locator.get("cell_range")),
        "pptx": bool(locator.get("slide_number") and (locator.get("shape_id") or locator.get("shape_ids"))),
        "pdf": bool(locator.get("page_start") and locator.get("page_end") and locator.get("bboxes")),
        "csv": bool(locator.get("row_start") and locator.get("row_end")),
        "json": bool(locator.get("json_path")),
        "eml": bool(locator.get("mime_part")),
        "html": isinstance(locator.get("element_index"), int) and locator.get("element_index") >= 1,
    }
    if precision == "exact" and not exact_evidence.get(fmt, False):
        errors.append("LOCATOR_PRECISION_INVALID")
    if fmt == "pdf" and precision == "page_only" and locator.get("bboxes"):
        errors.append("LOCATOR_PRECISION_INVALID")
    if fmt == "pdf" and precision == "exact" and not locator.get("bboxes"):
        errors.append("LOCATOR_PRECISION_INVALID")
    if fmt == "docx" and precision == "exact":
        errors.append("LOCATOR_PRECISION_INVALID")


def _validate_element_layout_and_associations(elements, by_id, errors):
    """Validate additive v1.8 layout hints and cross-element association edges."""
    reciprocal = {
        "caption_of": "captioned_by", "captioned_by": "caption_of",
        "note_for": "has_note", "has_note": "note_for",
    }
    sibling_orders = {}
    for element in elements:
        element_id = element.get("id")
        properties = element.get("properties") or {}
        layout = properties.get("layout") or {}
        if "reading_order" in layout:
            order = layout.get("reading_order")
            if not isinstance(order, int) or order < 1:
                errors.append(f"LAYOUT_READING_ORDER_INVALID: {element_id}")
            else:
                key = (element.get("parent_id"), order)
                if key in sibling_orders:
                    errors.append(
                        f"LAYOUT_READING_ORDER_DUPLICATE: {sibling_orders[key]} and {element_id}"
                    )
                sibling_orders[key] = element_id
        for edge in properties.get("associations") or []:
            relation = edge.get("relation")
            target_id = edge.get("target_id")
            if target_id == element_id:
                errors.append(f"ASSOCIATION_SELF_REFERENCE: {element_id}")
                continue
            target = by_id.get(target_id)
            if target is None:
                errors.append(f"ASSOCIATION_TARGET_MISSING: {element_id} -> {target_id}")
                continue
            inverse = reciprocal.get(relation)
            target_edges = (target.get("properties") or {}).get("associations") or []
            if inverse and not any(
                candidate.get("relation") == inverse
                and candidate.get("target_id") == element_id
                for candidate in target_edges
            ):
                errors.append(
                    f"ASSOCIATION_RECIPROCAL_MISSING: {element_id} {relation} {target_id}"
                )


def _ordered_unique(values):
    return list(dict.fromkeys(value for value in values if value is not None))


def _chunk_ancestor_ids(element, by_id):
    ancestors, visited = [], set()
    parent_id = element.get("parent_id")
    while parent_id and parent_id in by_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id[parent_id]
        if parent.get("type") != "document":
            ancestors.append(parent_id)
        parent_id = parent.get("parent_id")
    return list(reversed(ancestors))


def _chunk_nearest_context_id(element, by_id, element_types):
    if element.get("type") in element_types:
        return element.get("id")
    visited = set()
    parent_id = element.get("parent_id")
    while parent_id and parent_id in by_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id[parent_id]
        if parent.get("type") in element_types:
            return parent_id
        parent_id = parent.get("parent_id")
    return None


def _expected_chunk_context(chunk, by_id):
    elements = [by_id[element_id] for element_id in chunk.get("element_ids", [])
                if element_id in by_id]
    ancestor_ids = _ordered_unique(
        ancestor_id for element in elements
        for ancestor_id in _chunk_ancestor_ids(element, by_id)
    )
    section_ids = _ordered_unique(
        _chunk_nearest_context_id(element, by_id, {"heading"})
        for element in elements
    )
    unit_ids = _ordered_unique(
        _chunk_nearest_context_id(element, by_id, {"page", "slide", "sheet"})
        for element in elements
    )
    relationships = []
    for element in elements:
        for edge in (element.get("properties") or {}).get("associations") or []:
            relationships.append({
                "source_element_id": element.get("id"),
                "relation": edge.get("relation"),
                "target_element_id": edge.get("target_id"),
                "confidence": edge.get("confidence"),
                "evidence": list(edge.get("evidence") or []),
                "method": edge.get("method"),
            })
    related_ids = _ordered_unique(
        relationship.get("target_element_id") for relationship in relationships
    )
    layouts = [(element.get("properties") or {}).get("layout") or {}
               for element in elements]
    return {
        "ancestor_element_ids": ancestor_ids,
        "section_element_id": section_ids[0] if len(section_ids) == 1 else None,
        "unit_element_id": unit_ids[0] if len(unit_ids) == 1 else None,
        "related_element_ids": related_ids,
        "relation_types": _ordered_unique(
            relationship.get("relation") for relationship in relationships
        ),
        "relationships": relationships,
        "layout_region_ids": _ordered_unique(layout.get("region_id") for layout in layouts),
        "layout_zones": _ordered_unique(layout.get("layout_zone") for layout in layouts),
        "layout_order_methods": _ordered_unique(
            layout.get("order_method") for layout in layouts
        ),
        "column_indexes": _ordered_unique(layout.get("column_index") for layout in layouts),
        "context_element_ids": _ordered_unique([*ancestor_ids, *related_ids]),
    }


def _expected_context_prefix(chunk, expected):
    lines = []
    if chunk.get("heading_path"):
        lines.append("[heading_path: " + " > ".join(chunk["heading_path"]) + "]")
    if expected["section_element_id"]:
        lines.append(f"[section_element_id: {expected['section_element_id']}]")
    if expected["unit_element_id"]:
        lines.append(f"[unit_element_id: {expected['unit_element_id']}]")
    if expected["relation_types"]:
        lines.append("[relation_types: " + ", ".join(expected["relation_types"]) + "]")
    if expected["related_element_ids"]:
        lines.append("[related_element_ids: " + ", ".join(expected["related_element_ids"]) + "]")
    if expected["layout_region_ids"]:
        lines.append("[layout_region_ids: " + ", ".join(expected["layout_region_ids"]) + "]")
    selected = []
    for line in lines:
        candidate = "\n".join([*selected, line]) + "\n\n"
        if len(candidate) + len(chunk.get("text", "")) <= HARD_MAX_CHUNK_CHARS:
            selected.append(line)
    return (("\n".join(selected) + "\n\n") if selected else "",
            len(selected) != len(lines))


def _validate_chunk_consumer_contract(chunk, by_id, errors):
    """Validate the optional additive v1.8.1 consumer projection contract."""
    if chunk.get("consumer_contract_version") is None:
        return
    chunk_id = chunk.get("chunk_id")
    if chunk.get("consumer_contract_version") != "1.0":
        errors.append(f"CHUNK_CONTEXT_VERSION_UNSUPPORTED: {chunk_id}")
        return
    expected = _expected_chunk_context(chunk, by_id)
    for field, expected_value in expected.items():
        if chunk.get(field) != expected_value:
            errors.append(f"CHUNK_CONTEXT_DERIVATION_MISMATCH: {chunk_id} {field}")
    for field in ("ancestor_element_ids", "related_element_ids", "context_element_ids"):
        for element_id in chunk.get(field) or []:
            if element_id not in by_id:
                errors.append(f"CHUNK_CONTEXT_REFERENCE_MISSING: {chunk_id} {element_id}")
    section_id = chunk.get("section_element_id")
    if section_id is not None and (section_id not in by_id
                                   or by_id[section_id].get("type") != "heading"):
        errors.append(f"CHUNK_CONTEXT_SECTION_INVALID: {chunk_id} {section_id}")
    unit_id = chunk.get("unit_element_id")
    if unit_id is not None and (unit_id not in by_id
                                or by_id[unit_id].get("type") not in {"page", "slide", "sheet"}):
        errors.append(f"CHUNK_CONTEXT_UNIT_INVALID: {chunk_id} {unit_id}")

    expected_prefix, expected_truncated = _expected_context_prefix(chunk, expected)
    text = chunk.get("text", "")
    prefix = chunk.get("context_prefix", "")
    embedding_text = chunk.get("embedding_text", "")
    if chunk.get("context_policy") != "source_text_priority_v1":
        errors.append(f"CHUNK_CONTEXT_POLICY_INVALID: {chunk_id}")
    if prefix != expected_prefix or chunk.get("context_truncated") != expected_truncated:
        errors.append(f"CHUNK_CONTEXT_PREFIX_MISMATCH: {chunk_id}")
    if chunk.get("context_char_count") != len(prefix):
        errors.append(f"CHUNK_CONTEXT_CHAR_COUNT_MISMATCH: {chunk_id}")
    if embedding_text != prefix + text:
        errors.append(f"CHUNK_EMBEDDING_TEXT_MISMATCH: {chunk_id}")
    if chunk.get("embedding_char_count") != len(embedding_text):
        errors.append(f"CHUNK_EMBEDDING_CHAR_COUNT_MISMATCH: {chunk_id}")
    if len(embedding_text) > HARD_MAX_CHUNK_CHARS:
        errors.append(f"CHUNK_EMBEDDING_EXCEEDS_HARD_LIMIT: {chunk_id}")


def _validate_source_locator(locator: dict, errors: list) -> None:
    fmt = locator.get("format")
    if fmt not in LOCATOR_FORMATS:
        errors.append("INVALID_SOURCE_LOCATOR_FORMAT")
        return
    if fmt == "xlsx":
        if locator.get("sheet_name") is not None and (not isinstance(locator.get("sheet_name"), str) or not locator["sheet_name"].strip()): errors.append("INVALID_XLSX_SHEET_NAME")
        if locator.get("cell_range") is not None and not _valid_a1_range(locator.get("cell_range")): errors.append("INVALID_XLSX_CELL_RANGE")
    elif fmt == "pdf":
        a, b = locator.get("page_start"), locator.get("page_end")
        if not isinstance(a, int) or not isinstance(b, int) or a < 1 or b < a: errors.append("INVALID_PDF_PAGE_RANGE")
        for bbox in locator.get("bboxes") or []:
            if (not isinstance(bbox, list) or len(bbox) != 4 or not all(isinstance(x, (int,float)) and __import__('math').isfinite(x) for x in bbox) or bbox[2] < bbox[0] or bbox[3] < bbox[1]): errors.append("INVALID_PDF_BBOX")
    elif fmt == "pptx":
        if not isinstance(locator.get("slide_number"), int) or locator["slide_number"] < 1: errors.append("INVALID_PPTX_SLIDE_NUMBER")
        shapes = locator.get("shape_ids") or ([locator["shape_id"]] if locator.get("shape_id") is not None else [])
        if shapes and (not isinstance(shapes, list) or not all(isinstance(x,int) and x >= 1 for x in shapes)): errors.append("INVALID_PPTX_SHAPE_ID")
    elif fmt == "csv":
        a,b=locator.get("row_start"),locator.get("row_end")
        if not isinstance(a,int) or not isinstance(b,int) or a < 1 or b < a: errors.append("INVALID_CSV_ROW_RANGE")
    elif fmt == "json":
        if not isinstance(locator.get("json_path"),str) or not locator["json_path"].startswith("$"): errors.append("INVALID_JSON_PATH")


def _valid_a1_range(value) -> bool:
    if not isinstance(value, str): return False
    match = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", value)
    if not match: return False
    def col(s):
        n=0
        for char in s: n=n*26+ord(char)-64
        return n
    return int(match.group(2)) >= 1 and (match.group(4) is None or (col(match.group(1)), int(match.group(2))) <= (col(match.group(3)), int(match.group(4))))


def _validate_local_asset_target(root: Path, raw_target: str, code_prefix: str,
                                 errors: list, context: str) -> None:
    """Validate one local bundle-relative target independently of the CWD."""
    normalized = unquote(raw_target)
    parsed = urlparse(normalized)
    details = f"{context} raw_target={raw_target!r} normalized_path={normalized!r}"
    if (parsed.scheme == "file" or re.match(r"^[A-Za-z]:[\\/]", normalized)
            or normalized.startswith("\\") or normalized.startswith("/") or Path(normalized).is_absolute()):
        errors.append(f"{code_prefix}_ABSOLUTE: {details}; reason=absolute path")
        return
    resolved = (root / Path(normalized)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append(f"{code_prefix}_ESCAPES_BUNDLE: {details}; reason=path escapes bundle")
        return
    if not resolved.is_file():
        errors.append(f"{code_prefix}_MISSING: {details}; reason=file does not exist")


def _validate_markdown_image_targets(bundle_dir: str, errors: list) -> None:
    """Validate local inline image destinations without consulting the CWD."""
    markdown = Path(bundle_dir, "document.md").read_text(encoding="utf-8")
    root = Path(bundle_dir).resolve()
    for ref in parse_markdown_image_references(markdown):
        if urlparse(ref.normalized_target).scheme in ("http", "https", "data"):
            continue
        _validate_local_asset_target(
            root, ref.raw_target, "MARKDOWN_IMAGE_TARGET", errors,
            f"document.md line={ref.line_number}",
        )


def _validate_canonical_asset_targets(bundle_dir: str, elements: list, errors: list) -> None:
    """Validate every populated canonical element asset reference."""
    root = Path(bundle_dir).resolve()
    for element in elements:
        asset = element.get("asset")
        if not asset:
            continue
        if not isinstance(asset, str):
            errors.append(
                "CANONICAL_ASSET_TARGET_MISSING: "
                f"element_id={element.get('id')!r} raw_target={asset!r}; reason=asset must be a string"
            )
            continue
        _validate_local_asset_target(
            root, asset, "CANONICAL_ASSET_TARGET", errors,
            f"element_id={element.get('id')!r}",
        )


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
    properties = table.get("properties") or {}
    if properties.get("origin") == "ocr_table_candidate":
        if properties.get("decision") != "accepted": errors.append("OCR_TABLE_REJECTED_AS_CANONICAL")
        if not isinstance(table.get("confidence"), (int, float)) or not 0 <= table["confidence"] <= 1: errors.append("OCR_TABLE_CONFIDENCE_INVALID")
        if not isinstance(table.get("engine"), str) or not table["engine"]: errors.append("OCR_TABLE_DECISION_INVALID")
        locator = table.get("source_locator") or {}
        if locator.get("format") != "pdf" or not isinstance(locator.get("page_start"), int) or locator.get("page_start") < 1 or locator.get("page_end") != locator.get("page_start"): errors.append("OCR_TABLE_LOCATOR_INVALID")
    if table.get("source_format") != "html":
        return
    if not isinstance(grid, list) or any(not isinstance(row, list) for row in grid):
        errors.append("HTML_TABLE_GRID_NOT_RECTANGULAR")
        return
    if grid and any(len(row) != len(grid[0]) for row in grid): errors.append("HTML_TABLE_GRID_NOT_RECTANGULAR")
    locator = table.get("source_locator") or {}
    if not isinstance(locator.get("table_index"), int) or locator["table_index"] < 1: errors.append("HTML_TABLE_REFERENCE_MISSING")
    occupied = set()
    for merge in table.get("merged_cells") or []:
        r, c, rs, cs = (merge.get(k) for k in ("anchor_row", "anchor_column", "rowspan", "colspan"))
        if not all(isinstance(x, int) for x in (r, c, rs, cs)) or r < 0 or c < 0 or rs < 1 or cs < 1:
            errors.append("HTML_TABLE_SPAN_INVALID"); continue
        if r + rs > rows or c + cs > columns:
            errors.append("HTML_TABLE_SPAN_OUT_OF_BOUNDS"); continue
        if grid[r][c] != merge.get("value"): errors.append("HTML_TABLE_SPAN_INVALID")
        cells = {(rr, cc) for rr in range(r, r + rs) for cc in range(c, c + cs)}
        if occupied.intersection(cells): errors.append("HTML_TABLE_SPAN_OVERLAP")
        occupied.update(cells)


def _validate_html_metrics(report: dict, html_tables: list, errors: list) -> None:
    structure = (report.get("details") or {}).get("html_structure") or {}
    if not structure:
        return
    source, canonical = structure.get("source_metrics") or {}, structure.get("canonical_metrics") or {}
    actual_merges = sum(len(table.get("merged_cells") or []) for table in html_tables)
    actual_cells = sum(sum(len(row) for row in table.get("grid") or []) for table in html_tables)
    if canonical.get("table_count") != len(html_tables): errors.append("HTML_TABLE_COUNT_MISMATCH")
    if canonical.get("merged_cell_anchor_count") != actual_merges: errors.append("HTML_MERGE_COUNT_MISMATCH")
    if canonical.get("expanded_grid_cell_count") != actual_cells: errors.append("HTML_METRICS_MISMATCH")
    if source.get("table_count", 0) != canonical.get("table_count", 0): errors.append("HTML_TABLE_COUNT_MISMATCH")
    if source.get("merged_cell_anchor_count", 0) != canonical.get("merged_cell_anchor_count", 0): errors.append("HTML_MERGE_COUNT_MISMATCH")


def _validate_ocr_table_metrics(report, table_ids, bundle_dir, errors):
    details = report.get("details") or {}
    metrics = details.get("ocr_table_assessment")
    if not metrics: return
    keys = ("candidate_count", "accepted_count", "rejected_count", "fallback_to_text_count", "low_confidence_count")
    if any(not isinstance(metrics.get(k), int) or metrics[k] < 0 for k in keys):
        errors.append("OCR_TABLE_METRICS_MISMATCH"); return
    if metrics["candidate_count"] != metrics["accepted_count"] + metrics["rejected_count"] or metrics["fallback_to_text_count"] > metrics["rejected_count"]:
        errors.append("OCR_TABLE_METRICS_MISMATCH")
    accepted = 0
    for table_id in table_ids:
        path = os.path.join(bundle_dir, "tables", f"{table_id}.json")
        if os.path.isfile(path) and (_load_json(path).get("properties") or {}).get("origin") == "ocr_table_candidate": accepted += 1
    if accepted != metrics["accepted_count"]: errors.append("OCR_TABLE_ACCEPTED_COUNT_MISMATCH")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate a converted output bundle")
    parser.add_argument("bundle", help="Output bundle directory")
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if result["status"] == "passed" else 1)
