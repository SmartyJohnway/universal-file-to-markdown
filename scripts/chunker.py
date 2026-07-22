"""Build bounded, hierarchy-aware chunks for RAG ingestion (v1.6)."""

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


def build_chunk_provenance(elements: list, by_id: dict) -> dict:
    """Produce deterministic provenance for one or more canonical elements."""
    locators = [_resolved_locator(element, by_id) for element in elements]
    precisions = [element.get("locator_precision", "unknown") for element in elements]
    table_ids = list(dict.fromkeys(element["table_id"] for element in elements if element.get("table_id")))
    # A chunk made from one element is precise exactly as that element is.
    if len(locators) == 1:
        result = {"source_locator": locators[0], "locator_precision": precisions[0]}
    else:
        unique = []
        for locator in locators:
            if locator not in unique:
                unique.append(locator)
        result = {"source_locators": unique, "locator_precision": "range"}
    if table_ids:
        result["table_ids"] = table_ids
    return result

def build_chunks(markdown: str, elements: list, sha256: str) -> list:
    if not elements:
        source_parts = _split_markdown(markdown)
        return [_chunk(i, [], [], part, sha256, 1, len(source_parts))
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
        return [_chunk(i, [], [], part, sha256, 1, len(source_parts))
                for i, part in enumerate(source_parts, start=1)]

    chunks = []
    for element in content_elements:
        parts = _split_markdown(element.get("content", ""))
        heading_path = list(element.get("heading_path") or []) or _ancestor_labels(element, by_id)
        if element.get("type") == "heading":
            heading_path = heading_path + [(element.get("content") or "").lstrip("# ")]
        for part_index, part in enumerate(parts, start=1):
            provenance = build_chunk_provenance([element], by_id)
            chunks.append(_chunk(len(chunks) + 1, heading_path, [element.get("id")],
                                 part, sha256, part_index, len(parts), provenance))
    return chunks


def _chunk(counter, heading_path, element_ids, text, sha256, part_index, part_count,
           provenance=None):
    provenance = provenance or {"locator_precision": "unknown"}
    locator = provenance.get("source_locator") or {}
    page = locator.get("page_start", locator.get("page"))
    slide = locator.get("slide_number", locator.get("slide"))
    return {
        "schema_version": "1.0",
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
        "source_file": locator.get("source_file"),
        "page_start": page,
        "page_end": locator.get("page_end", page),
        "sheet_name": locator.get("sheet_name", locator.get("sheet")),
        "slide_start": slide,
        "slide_end": slide,
        "source_sha256": sha256,
        **({"source_locator": locator} if "source_locator" in provenance else {"source_locators": provenance["source_locators"]} if "source_locators" in provenance else {}),
    }
