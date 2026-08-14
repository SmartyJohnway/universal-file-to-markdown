"""Build bounded, hierarchy-aware chunks for RAG ingestion (v1.6)."""

import json
import re


MAX_CHUNK_CHARS = 2000
HARD_MAX_CHUNK_CHARS = 2000


def _split_long_line(line: str, limit: int) -> list:
    parts = []
    rest = line
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit + 1)
        if cut < max(1, limit // 2):
            cut = limit
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        parts.append(rest)
    return parts


def _split_markdown(text: str, limit: int = MAX_CHUNK_CHARS) -> list:
    """Split at paragraphs/rows/lines, then at word boundaries as a last
    resort. Every emitted part is guaranteed to be <= ``limit`` chars."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    blocks = re.split(r"\n\s*\n", text)
    units = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(block) <= limit:
            units.append(block)
            continue
        # Markdown table rows, HTML <tr> rows, lists, and ordinary lines all
        # get a stable boundary here before the hard word-boundary fallback.
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if (len(lines) >= 2 and lines[0].startswith("|")
                and re.match(r"^\|?\s*:?-+", lines[1])):
            units.extend(_split_pipe_table(lines, limit))
            continue
        for line in lines:
            units.extend(_split_long_line(line, limit))

    parts, current = [], ""
    for unit in units:
        candidate = unit if not current else current + "\n\n" + unit
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = unit
    if current:
        parts.append(current)
    return parts


def _split_pipe_table(lines: list, limit: int) -> list:
    header = "\n".join(lines[:2])
    if len(header) > limit:
        return [part for line in lines for part in _split_long_line(line, limit)]
    parts = []
    current = header
    for row in lines[2:]:
        candidate = current + "\n" + row
        if len(candidate) <= limit:
            current = candidate
            continue
        if current != header:
            parts.append(current)
            current = header
        if len(header) + 1 + len(row) <= limit:
            current += "\n" + row
        else:
            # A pathological single row cannot stay intact and honor the hard
            # limit. Split it safely as the final fallback and retain the
            # repeated header on every emitted part where it fits.
            room = max(1, limit - len(header) - 1)
            for row_part in _split_long_line(row, room):
                parts.append(header + "\n" + row_part)
    if current != header or not parts:
        parts.append(current)
    return parts


def _ancestor_labels(element: dict, by_id: dict) -> list:
    labels = []
    parent_id = element.get("parent_id")
    visited = set()
    while parent_id and parent_id in by_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id[parent_id]
        ptype = parent.get("type")
        if ptype == "sheet":
            labels.append(f"Sheet: {parent.get('sheet_name', '?')}")
        elif ptype == "page":
            labels.append(f"Page {parent.get('page', '?')}")
        elif ptype == "slide":
            labels.append(f"Slide {parent.get('slide', '?')}")
        elif ptype == "heading":
            labels.append((parent.get("content") or "").lstrip("# "))
        parent_id = parent.get("parent_id")
    return list(reversed([label for label in labels if label]))


def _resolved_locator(element: dict, by_id: dict) -> dict:
    """Resolve a canonical element locator, inheriting absent fields from parents."""
    resolved, current, visited = {}, element, set()
    while current and current.get("id") not in visited:
        visited.add(current.get("id"))
        for key, value in (current.get("source_locator") or {}).items():
            if value is not None and key not in resolved:
                resolved[key] = value
        current = by_id.get(current.get("parent_id"))
    return resolved


def _ordered_unique(values) -> list:
    return list(dict.fromkeys(value for value in values if value is not None))


def _ancestor_ids(element: dict, by_id: dict) -> list:
    ancestors = []
    parent_id = element.get("parent_id")
    visited = set()
    while parent_id and parent_id in by_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id[parent_id]
        if parent.get("type") != "document":
            ancestors.append(parent_id)
        parent_id = parent.get("parent_id")
    return list(reversed(ancestors))


def _nearest_ancestor_id(element: dict, by_id: dict, types: set[str]):
    if element.get("type") in types:
        return element.get("id")
    parent_id = element.get("parent_id")
    visited = set()
    while parent_id and parent_id in by_id and parent_id not in visited:
        visited.add(parent_id)
        parent = by_id[parent_id]
        if parent.get("type") in types:
            return parent_id
        parent_id = parent.get("parent_id")
    return None


def _a1_bounds(cell_range: str):
    match = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)(?::\$?([A-Z]+)\$?(\d+))?", cell_range or "")
    if not match:
        return None
    def column(value):
        result = 0
        for character in value:
            result = result * 26 + ord(character) - 64
        return result
    end_column, end_row = match.group(3) or match.group(1), match.group(4) or match.group(2)
    return column(match.group(1)), int(match.group(2)), column(end_column), int(end_row)


def _a1_label(min_col, min_row, max_col, max_row):
    def column(value):
        result = ""
        while value:
            value, remainder = divmod(value - 1, 26)
            result = chr(65 + remainder) + result
        return result
    return f"{column(min_col)}{min_row}:{column(max_col)}{max_row}"


def _rectangles_form_contiguous_rectangle(bounds: list[tuple[int, int, int, int]]) -> bool:
    """Only merge XLSX ranges when their union has no unclaimed cells."""
    min_col, min_row = min(x[0] for x in bounds), min(x[1] for x in bounds)
    max_col, max_row = max(x[2] for x in bounds), max(x[3] for x in bounds)
    # Exact occupancy check avoids fabricating a bounding source area. Typical
    # extracted blocks are small; huge ranges are accepted only when every
    # range already spans one complete bounding dimension.
    area = (max_col - min_col + 1) * (max_row - min_row + 1)
    if area <= 1_000_000:
        covered = set()
        for left, top, right, bottom in bounds:
            covered.update((col, row) for col in range(left, right + 1) for row in range(top, bottom + 1))
        return len(covered) == area
    return all((left == min_col and right == max_col) or (top == min_row and bottom == max_row)
               for left, top, right, bottom in bounds)


def merge_source_locators(locators: list[dict]) -> tuple[dict | list[dict], str]:
    """Merge compatible locators; preserve disjoint sources as a list."""
    unique = list(dict.fromkeys(json.dumps(x, sort_keys=True) for x in locators))
    locators = [json.loads(value) for value in unique]
    if len(locators) == 1:
        return locators[0], "exact"
    formats = {locator.get("format") for locator in locators}
    if len(formats) != 1:
        return locators, "range"
    fmt = formats.pop()
    if fmt == "xlsx" and len({x.get("sheet_name") for x in locators}) == 1:
        bounds = [_a1_bounds(x.get("cell_range")) for x in locators]
        if all(bounds) and _rectangles_form_contiguous_rectangle(bounds):
            return {"format": fmt, "sheet_name": locators[0]["sheet_name"], "cell_range": _a1_label(min(x[0] for x in bounds), min(x[1] for x in bounds), max(x[2] for x in bounds), max(x[3] for x in bounds))}, "range"
    if fmt == "pptx" and len({x.get("slide_number") for x in locators}) == 1:
        shapes = sorted({shape for x in locators for shape in (x.get("shape_ids") or [x.get("shape_id")]) if shape is not None})
        if shapes:
            return {"format": fmt, "slide_number": locators[0]["slide_number"], "shape_ids": shapes}, "range"
    if fmt == "pdf":
        starts, ends = [x.get("page_start") for x in locators], [x.get("page_end") for x in locators]
        if all(isinstance(x, int) for x in starts + ends) and max(starts) <= min(ends) + 1:
            merged = {"format": fmt, "page_start": min(starts), "page_end": max(ends)}
            bboxes = [bbox for x in locators for bbox in (x.get("bboxes") or [])]
            if bboxes and merged["page_start"] == merged["page_end"]: merged["bboxes"] = bboxes
            return merged, "range"
    for start, end in (("element_start", "element_end"), ("paragraph_start", "paragraph_end"), ("row_start", "row_end")):
        if all(isinstance(x.get(start), int) and isinstance(x.get(end), int) for x in locators):
            shared = "section_index" not in locators[0] or len({x.get("section_index") for x in locators}) == 1
            if shared and max(x[start] for x in locators) <= min(x[end] for x in locators) + 1:
                merged = {"format": fmt, start: min(x[start] for x in locators), end: max(x[end] for x in locators)}
                if "section_index" in locators[0]: merged["section_index"] = locators[0]["section_index"]
                return merged, "range"
    return locators, "range"


def build_chunk_provenance(elements: list, by_id: dict) -> dict:
    """Collect element/table references and merge compatible source locators."""
    locators = [_resolved_locator(element, by_id) for element in elements]
    table_ids = list(dict.fromkeys(element["table_id"] for element in elements if element.get("table_id")))
    merged, precision = merge_source_locators(locators)
    if len(locators) == 1:
        precision = elements[0].get("locator_precision", "unknown")
    result = ({"source_locator": merged} if isinstance(merged, dict) else {"source_locators": merged})
    result["locator_precision"] = precision
    if table_ids: result["table_ids"] = table_ids
    ancestor_element_ids = _ordered_unique(
        ancestor_id
        for element in elements
        for ancestor_id in _ancestor_ids(element, by_id)
    )
    section_ids = _ordered_unique(
        _nearest_ancestor_id(element, by_id, {"heading"}) for element in elements
    )
    unit_ids = _ordered_unique(
        _nearest_ancestor_id(element, by_id, {"page", "slide", "sheet"})
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
    related_element_ids = _ordered_unique(
        relationship.get("target_element_id") for relationship in relationships
    )
    layout_values = [
        (element.get("properties") or {}).get("layout") or {}
        for element in elements
    ]
    layout_region_ids = _ordered_unique(value.get("region_id") for value in layout_values)
    layout_zones = _ordered_unique(value.get("layout_zone") for value in layout_values)
    layout_order_methods = _ordered_unique(value.get("order_method") for value in layout_values)
    column_indexes = _ordered_unique(value.get("column_index") for value in layout_values)
    result.update({
        "ancestor_element_ids": ancestor_element_ids,
        "section_element_id": section_ids[0] if len(section_ids) == 1 else None,
        "unit_element_id": unit_ids[0] if len(unit_ids) == 1 else None,
        "related_element_ids": related_element_ids,
        "relation_types": _ordered_unique(
            relationship.get("relation") for relationship in relationships
        ),
        "relationships": relationships,
        "layout_region_ids": layout_region_ids,
        "layout_zones": layout_zones,
        "layout_order_methods": layout_order_methods,
        "column_indexes": column_indexes,
        "context_element_ids": _ordered_unique(
            [*ancestor_element_ids, *related_element_ids]
        ),
    })
    return result


def _build_context_prefix(heading_path, provenance, text: str) -> tuple[str, bool]:
    """Use only remaining embedding budget; canonical source text always wins."""
    lines = []
    if heading_path:
        lines.append("[heading_path: " + " > ".join(str(value) for value in heading_path) + "]")
    if provenance.get("section_element_id"):
        lines.append(f"[section_element_id: {provenance['section_element_id']}]")
    if provenance.get("unit_element_id"):
        lines.append(f"[unit_element_id: {provenance['unit_element_id']}]")
    if provenance.get("relation_types"):
        lines.append("[relation_types: " + ", ".join(provenance["relation_types"]) + "]")
    if provenance.get("related_element_ids"):
        lines.append("[related_element_ids: " + ", ".join(provenance["related_element_ids"]) + "]")
    if provenance.get("layout_region_ids"):
        lines.append("[layout_region_ids: " + ", ".join(provenance["layout_region_ids"]) + "]")

    selected = []
    for line in lines:
        candidate_lines = [*selected, line]
        candidate_prefix = "\n".join(candidate_lines) + "\n\n"
        if len(candidate_prefix) + len(text) <= HARD_MAX_CHUNK_CHARS:
            selected.append(line)
    prefix = ("\n".join(selected) + "\n\n") if selected else ""
    return prefix, len(selected) != len(lines)


def build_chunks(markdown: str, elements: list, sha256: str, source_file: str = None) -> list:
    if not elements:
        source_parts = _split_markdown(markdown)
        return [_chunk(i, [], [], part, sha256, 1, len(source_parts), source_file=source_file)
                for i, part in enumerate(source_parts, start=1)]

    by_id = {el.get("id"): el for el in elements if el.get("id")}
    content_elements = [
        el for el in elements
        if el.get("type") != "document"
        and not el.get("child_ids")
        and (el.get("content") or "").strip()
    ]
    if not content_elements:
        source_parts = _split_markdown(markdown)
        return [_chunk(i, [], [], part, sha256, 1, len(source_parts), source_file=source_file)
                for i, part in enumerate(source_parts, start=1)]

    chunks, pending, pending_text, pending_heading = [], [], "", None
    def emit_pending():
        if pending:
            provenance = build_chunk_provenance(pending, by_id)
            chunks.append(_chunk(len(chunks) + 1, pending_heading, [e["id"] for e in pending], pending_text, sha256, 1, 1, provenance, source_file))
    for element in content_elements:
        parts = _split_markdown(element.get("content", ""))
        heading_path = list(element.get("heading_path") or []) or _ancestor_labels(element, by_id)
        is_heading = element.get("type") == "heading"
        if is_heading:
            heading_path = heading_path + [(element.get("content") or "").lstrip("# ")]
        if is_heading or len(parts) != 1 or (pending and (element.get("parent_id") != pending[-1].get("parent_id") or pending_heading != heading_path or len(pending_text) + len(parts[0]) + 2 > MAX_CHUNK_CHARS)):
            emit_pending(); pending, pending_text, pending_heading = [], "", None
        if len(parts) == 1:
            pending.append(element); pending_text = parts[0] if not pending_text else pending_text + "\n\n" + parts[0]; pending_heading = heading_path
            if is_heading:
                emit_pending(); pending, pending_text, pending_heading = [], "", None
        else:
            for part_index, part in enumerate(parts, start=1):
                chunks.append(_chunk(len(chunks) + 1, heading_path, [element["id"]], part, sha256, part_index, len(parts), build_chunk_provenance([element], by_id), source_file))
    emit_pending()
    return chunks


def _chunk(counter, heading_path, element_ids, text, sha256, part_index, part_count,
           provenance=None, source_file=None):
    provenance = provenance or {"locator_precision": "unknown"}
    locator = provenance.get("source_locator") or {}
    page = locator.get("page_start", locator.get("page"))
    slide = locator.get("slide_number", locator.get("slide"))
    context_prefix, context_truncated = _build_context_prefix(
        heading_path or [], provenance, text
    )
    embedding_text = context_prefix + text
    return {
        "schema_version": "1.0",
        "consumer_contract_version": "1.0",
        "chunk_id": f"chunk-{counter:05d}",
        "heading_path": heading_path,
        "element_ids": element_ids,
        "table_ids": provenance.get("table_ids", []),
        "locator_precision": provenance["locator_precision"],
        "text": text,
        "char_count": len(text),
        "part_index": part_index,
        "part_count": part_count,
        "chunk_index": counter,
        "source_file": locator.get("source_file") or source_file,
        "page_start": page,
        "page_end": locator.get("page_end", page),
        "sheet_name": locator.get("sheet_name", locator.get("sheet")),
        "slide_start": slide,
        "slide_end": slide,
        "source_sha256": sha256,
        "ancestor_element_ids": provenance.get("ancestor_element_ids", []),
        "section_element_id": provenance.get("section_element_id"),
        "unit_element_id": provenance.get("unit_element_id"),
        "related_element_ids": provenance.get("related_element_ids", []),
        "relation_types": provenance.get("relation_types", []),
        "relationships": provenance.get("relationships", []),
        "layout_region_ids": provenance.get("layout_region_ids", []),
        "layout_zones": provenance.get("layout_zones", []),
        "layout_order_methods": provenance.get("layout_order_methods", []),
        "column_indexes": provenance.get("column_indexes", []),
        "context_element_ids": provenance.get("context_element_ids", []),
        "context_policy": "source_text_priority_v1",
        "context_prefix": context_prefix,
        "context_char_count": len(context_prefix),
        "context_truncated": context_truncated,
        "embedding_text": embedding_text,
        "embedding_char_count": len(embedding_text),
        **({"source_locator": locator} if "source_locator" in provenance else {"source_locators": provenance["source_locators"]} if "source_locators" in provenance else {}),
    }
