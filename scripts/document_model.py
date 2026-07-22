"""Build the v1.6 canonical, hierarchical document model.

Converters emit an ordered flat list with optional ``parent_id`` values.
This module adds one synthetic document root, normalizes the public schema,
validates IDs/parent references, and materializes ``child_ids``.  Keeping the
storage flat avoids recursive duplication while still making hierarchy
explicit and easy for RAG/indexing consumers to traverse.
"""

import os


SCHEMA_VERSION = "1.0"
_ELEMENT_DEFAULTS = {
    "parent_id": None,
    "children": None,
    "child_ids": None,
    "content": "",
    "content_format": "markdown",
    "heading_path": None,
    "engine": None,
    "confidence": None,
    "source_locator": None,
    "locator_precision": None,
    "properties": None,
    "warnings": None,
}

_LOCATOR_DEFAULTS = {
    "page": None, "slide": None, "sheet": None, "cell_range": None,
    "shape_id": None, "shape_name": None, "bbox": None,
    "table_index": None, "relationship_id": None, "part": None,
    "source_file": None,
    "format": None, "sheet_name": None, "anchor_cell": None,
    "cell_range": None, "slide_number": None, "shape_ids": None,
    "page_start": None, "page_end": None, "bboxes": None,
    "section_index": None, "element_start": None, "element_end": None,
    "row_start": None, "row_end": None, "json_path": None,
    "mime_part": None, "section": None, "filename": None,
    "element_index": None, "element_id": None,
}


def _normalize_element(el: dict, default_engine: str, ordinal: int, file_type: str) -> dict:
    normalized = dict(_ELEMENT_DEFAULTS)
    normalized.update(el)
    normalized["ordinal"] = ordinal
    if normalized.get("engine") is None:
        normalized["engine"] = default_engine
    locator = dict(_LOCATOR_DEFAULTS)
    supplied_locator = normalized.get("source_locator") or {}
    supplied_locator = dict(supplied_locator)
    if "sheet_name" in supplied_locator and "sheet" not in supplied_locator:
        supplied_locator["sheet"] = supplied_locator.pop("sheet_name")
    if "range" in supplied_locator and "cell_range" not in supplied_locator:
        supplied_locator["cell_range"] = supplied_locator.pop("range")
    # Normalize legacy locator names into the public source-locator contract.
    if "sheet" in supplied_locator and "sheet_name" not in supplied_locator:
        supplied_locator["sheet_name"] = supplied_locator["sheet"]
    if "slide" in supplied_locator and "slide_number" not in supplied_locator:
        supplied_locator["slide_number"] = supplied_locator["slide"]
    if "page" in supplied_locator:
        supplied_locator.setdefault("page_start", supplied_locator["page"])
        supplied_locator.setdefault("page_end", supplied_locator["page"])
    if "bbox" in supplied_locator and supplied_locator["bbox"] is not None:
        supplied_locator.setdefault("bboxes", [supplied_locator["bbox"]])
    supplied_locator.setdefault("format", file_type)
    if file_type == "docx":
        supplied_locator.setdefault("section_index", 0)
        supplied_locator.setdefault("element_start", ordinal)
        supplied_locator.setdefault("element_end", ordinal)
    locator.update(supplied_locator)
    normalized["source_locator"] = locator
    precision = normalized.get("locator_precision")
    if precision is None:
        if file_type == "pdf":
            precision = "derived" if "ocr" in str(normalized.get("engine", "")).lower() and locator.get("page_start") else ("exact" if locator.get("bboxes") else ("page_only" if locator.get("page_start") else "unknown"))
        elif file_type == "docx":
            precision = "range"
        elif file_type in {"xlsx", "pptx", "csv", "json", "eml"}:
            precision = "exact" if ((file_type == "xlsx" and locator.get("cell_range")) or (file_type == "pptx" and locator.get("shape_id")) or (file_type == "csv" and locator.get("row_start") is not None) or (file_type == "json" and locator.get("json_path")) or (file_type == "eml" and locator.get("mime_part"))) else "unknown"
        elif file_type == "html":
            precision = "exact" if locator.get("element_index") is not None else "unknown"
        else:
            precision = "unknown"
    normalized["locator_precision"] = precision
    normalized["heading_path"] = list(normalized.get("heading_path") or [])
    normalized["properties"] = dict(normalized.get("properties") or {})
    normalized["warnings"] = list(normalized.get("warnings") or [])
    normalized["children"] = []
    normalized["child_ids"] = []
    return normalized


def build_document_json(source_path: str, sha256: str, file_type: str, elements: list,
                        default_engine: str = None) -> dict:
    root_id = "document-root"
    root = _normalize_element({
        "id": root_id,
        "type": "document",
        "content": "",
        "engine": default_engine,
        "source_locator": {"source_file": os.path.basename(source_path)},
    }, default_engine, 0, file_type)

    normalized = [root]
    seen = {root_id}
    for ordinal, element in enumerate(elements, start=1):
        item = _normalize_element(element, default_engine, ordinal, file_type)
        element_id = item.get("id")
        if not isinstance(element_id, str) or not element_id.strip():
            raise ValueError(f"element at ordinal {ordinal} has no valid id")
        if element_id in seen:
            raise ValueError(f"duplicate element id: {element_id}")
        seen.add(element_id)
        if item.get("parent_id") is None:
            item["parent_id"] = root_id
        normalized.append(item)

    by_id = {item["id"]: item for item in normalized}
    for item in normalized[1:]:
        parent_id = item["parent_id"]
        if parent_id not in by_id:
            raise ValueError(f"element {item['id']} references missing parent {parent_id}")
        if parent_id == item["id"]:
            raise ValueError(f"element {item['id']} cannot parent itself")

    for item in normalized[1:]:
        current_id = item["id"]
        path = set()
        while current_id != root_id:
            if current_id in path:
                raise ValueError(f"hierarchy cycle detected at element {current_id}")
            path.add(current_id)
            current_id = by_id[current_id]["parent_id"]

    for item in normalized[1:]:
        parent_id = item["parent_id"]
        by_id[parent_id]["child_ids"].append(item["id"])
        by_id[parent_id]["children"].append(item["id"])

    return {
        "schema_version": SCHEMA_VERSION,
        "source_file": os.path.basename(source_path),
        "source_sha256": sha256,
        "file_type": file_type,
        "root_element_id": root_id,
        "element_count": len(normalized),
        "content_element_count": len(normalized) - 1,
        "elements": normalized,
    }
