"""Deterministic native HTML structure extraction using BeautifulSoup + lxml."""
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


def parse_html_source(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return BeautifulSoup(handle.read(), "lxml")


def extract_main_content(soup):
    candidates = (("main_element", "main", "high", soup.find("main")),
                  ("article_element", "article", "high", soup.find("article")),
                  ("role_main", '[role="main"]', "high", soup.find(attrs={"role": "main"})),
                  ("content_id", "#content", "medium", soup.find(id="content")),
                  ("content_class", ".content", "medium", soup.find(class_="content")),
                  ("body_fallback", "body", "low", soup.body))
    for strategy, selector, confidence, node in candidates:
        if node:
            warnings = [] if confidence != "low" else ["MAIN_CONTENT_NOT_IDENTIFIED", "BOILERPLATE_MAY_BE_INCLUDED"]
            return node, {"strategy": strategy, "selector": selector, "confidence": confidence}, warnings
    return soup, {"strategy": "document_fallback", "selector": "document", "confidence": "low"}, ["MAIN_CONTENT_NOT_IDENTIFIED", "BOILERPLATE_MAY_BE_INCLUDED"]


def _relative(value):
    parsed = urlparse(value or "")
    return bool(value) and not parsed.scheme and not value.startswith("//")


def resolve_url(value, base_url, warnings):
    if not value:
        return value
    if value.startswith("//"):
        return "https:" + value
    if not _relative(value):
        return value
    if base_url:
        return urljoin(base_url, value)
    warnings.update(("BASE_URL_UNAVAILABLE", "RELATIVE_URL_UNRESOLVED"))
    return value


def _text(node):
    return " ".join(node.stripped_strings)


def _markdown_inline(node, base_url, warnings, emitted_urls, emitted_images=None):
    """Preserve links/images while flattening only inline HTML markup."""
    parts = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.name == "a":
            url = resolve_url(child.get("href"), base_url, warnings)
            label = _markdown_inline(child, base_url, warnings, emitted_urls, emitted_images).strip() or url or ""
            if url:
                emitted_urls.append((id(child), url))
                parts.append(f"[{label}]({url})")
            else:
                parts.append(label)
        elif child.name == "img":
            url = resolve_url(child.get("src"), base_url, warnings)
            if url:
                if emitted_images is not None:
                    emitted_images.append({"source_node_id": id(child), "url": url})
                parts.append(f"![{child.get('alt', '')}]({url})")
        elif child.name == "br":
            parts.append("<br>")
        else:
            parts.append(_markdown_inline(child, base_url, warnings, emitted_urls, emitted_images))
    return "".join(parts).strip()


def extract_cell_blocks(cell, base_url, warnings):
    blocks = []
    for node in cell.find_all(["p", "br", "li", "a", "img"], recursive=True):
        if node.name == "br": blocks.append({"type": "line_break"})
        elif node.name == "li": blocks.append({"type": "list_item", "level": len(node.find_parents(["ul", "ol"])), "ordered": bool(node.find_parent("ol")), "text": _text(node)})
        elif node.name == "a": blocks.append({"type": "link", "text": _text(node), "url": resolve_url(node.get("href"), base_url, warnings)})
        elif node.name == "img": blocks.append({"type": "image", "alt": node.get("alt", ""), "url": resolve_url(node.get("src"), base_url, warnings), "remote_resource": True})
        elif node.name == "p": blocks.append({"type": "paragraph", "text": _text(node)})
    return blocks or [{"type": "paragraph", "text": _text(cell)}]


def _span(cell, name, warnings):
    try:
        value = int(cell.get(name, "1"))
        if value < 1: raise ValueError
        return value
    except (TypeError, ValueError):
        warnings.add("HTML_TABLE_SPAN_INVALID")
        return 1


def extract_table(table, index, base_url, warnings):
    occupied, cells, merges, cell_blocks, grid = {}, [], [], [], []
    source_cells = 0
    for row_index, tr in enumerate(table.find_all("tr")):
        column = 0
        while (row_index, column) in occupied: column += 1
        for cell in tr.find_all(["th", "td"], recursive=False):
            while (row_index, column) in occupied: column += 1
            source_cells += 1
            rowspan, colspan = _span(cell, "rowspan", warnings), _span(cell, "colspan", warnings)
            value = _text(cell)
            positions = [(r, c) for r in range(row_index, row_index + rowspan) for c in range(column, column + colspan)]
            if any(position in occupied for position in positions):
                # Preserve the first source anchor; never silently overwrite it.
                warnings.add("HTML_TABLE_SPAN_OVERLAP")
                column += colspan
                continue
            for position in positions: occupied[position] = value
            cells.append({"row": row_index, "column": column, "value": value, "rowspan": rowspan, "colspan": colspan, "is_header": cell.name == "th"})
            if rowspan > 1 or colspan > 1:
                merges.append({"anchor_row": row_index, "anchor_column": column, "rowspan": rowspan, "colspan": colspan, "value": value})
            blocks = extract_cell_blocks(cell, base_url, warnings)
            if len(blocks) > 1 or blocks[0].get("type") != "paragraph": cell_blocks.append({"row": row_index, "column": column, "blocks": blocks})
            column += colspan
    row_count = max((r for r, _ in occupied), default=-1) + 1
    width = max((c for _, c in occupied), default=-1) + 1
    for r in range(row_count): grid.append([occupied.get((r, c), "") for c in range(width)])
    if not grid: warnings.add("HTML_TABLE_EMPTY")
    locator = {"format": "html", "table_index": index}
    if table.get("id"): locator["element_id"] = table["id"]
    return {"id": f"table-html-{index:04d}", "source_format": "html", "source_locator": locator,
            "source_dimensions": {"row_count": len(table.find_all("tr")), "source_cell_count": source_cells},
            "grid": grid, "cells": cells, "merged_cells": merges, "cell_blocks": cell_blocks, "engine": "beautifulsoup4_lxml"}


def render_table(grid):
    if not grid: return ""
    escape = lambda value: str(value).replace("|", "\\|").replace("\n", "<br>")
    return "\n".join(["| " + " | ".join(escape(x) for x in grid[0]) + " |", "| " + " | ".join("---" for _ in grid[0]) + " |"] + ["| " + " | ".join(escape(x) for x in row) + " |" for row in grid[1:]])


def extract_html(path, source_url=None):
    soup = parse_html_source(path)
    base_url = source_url or (soup.base.get("href") if soup.base else None)
    main, main_content, warning_codes = extract_main_content(soup)
    warnings, emitted_urls, emitted_images, elements, tables = set(warning_codes), [], [], [], []
    for node in main.find_all(["script", "style", "noscript", "template"]): node.decompose()
    heading_stack, ordinal, table_index = [], 0, 0

    def add(kind, content, node, parent_id=None, properties=None):
        nonlocal ordinal
        ordinal += 1
        locator = {"format": "html", "element_index": ordinal}
        if node.get("id"): locator["element_id"] = node["id"]
        element = {"id": f"html-{kind}-{ordinal:04d}", "type": kind, "content": content,
                   "heading_path": [item[1] for item in heading_stack], "source_locator": locator,
                   "locator_precision": "exact", "properties": properties or {}}
        if parent_id: element["parent_id"] = parent_id
        elements.append(element); return element

    def emit_list(list_node, parent_id=None, level=1):
        ordered = list_node.name == "ol"
        container = add("list", "", list_node, parent_id, {"ordered": ordered, "level": level})
        for li in list_node.find_all("li", recursive=False):
            inline = _markdown_inline(li, base_url, warnings, emitted_urls, emitted_images)
            # Nested list text is excluded from the item readable projection.
            for nested in li.find_all(["ul", "ol"], recursive=False): inline = inline.replace(_text(nested), "").strip()
            marker = "1." if ordered else "-"
            item = add("list_item", f"{'  ' * (level - 1)}{marker} {inline}", li, container["id"], {"ordered": ordered, "level": level})
            for nested in li.find_all(["ul", "ol"], recursive=False): emit_list(nested, item["id"], level + 1)
        return container

    def walk_blocks(container):
        """Give each semantic DOM node exactly one renderer/owner.

        Paragraph and list renderers consume their inline descendants, so only
        transparent wrapper nodes recurse.  This prevents a list paragraph or
        inline image from being emitted a second time by a flat descendant scan.
        """
        nonlocal table_index, heading_stack
        for node in container.children:
            if not getattr(node, "name", None) or node.name in ("script", "style", "noscript", "template"):
                continue
            parent = heading_stack[-1][0] if heading_stack else None
            if node.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level, text = int(node.name[1]), _text(node)
                heading_stack = heading_stack[:level - 1]
                parent = heading_stack[-1][0] if heading_stack else None
                heading = add("heading", "#" * level + " " + text, node, parent, {"level": level})
                heading_stack.append((heading["id"], text))
            elif node.name in ("ul", "ol"):
                emit_list(node, parent)
            elif node.name == "table":
                table_index += 1
                table = extract_table(node, table_index, base_url, warnings)
                tables.append(table)
                element = add("table", render_table(table["grid"]), node, parent)
                element["table_id"] = table["id"]
                for image in node.find_all("img"):
                    url = resolve_url(image.get("src"), base_url, warnings)
                    if url:
                        emitted_images.append({"source_node_id": id(image), "url": url})
            elif node.name == "img":
                url = resolve_url(node.get("src"), base_url, warnings)
                if url:
                    emitted_images.append({"source_node_id": id(node), "url": url})
                add("image", f"![{node.get('alt', '')}]({url or ''})", node, parent, {"remote_resource": True, "url": url})
            elif node.name == "p":
                content = _markdown_inline(node, base_url, warnings, emitted_urls, emitted_images)
                if content:
                    add("paragraph", content, node, parent)
            else:
                walk_blocks(node)

    walk_blocks(main)
    # Links can occur in non-semantic wrapper elements. Preserve any that did
    # not belong to an emitted paragraph/list item instead of claiming them in
    # metrics without canonical evidence.
    emitted_anchor_ids = {anchor_id for anchor_id, _ in emitted_urls}
    parent = heading_stack[-1][0] if heading_stack else None
    for anchor in main.find_all("a"):
        if id(anchor) in emitted_anchor_ids:
            continue
        url = resolve_url(anchor.get("href"), base_url, warnings)
        label = _text(anchor) or url or ""
        if url:
            emitted_urls.append((id(anchor), url))
            add("paragraph", f"[{label}]({url})", anchor, parent, {"link_only_fallback": True})
    source = {"heading_count": len(main.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])), "table_count": len(main.find_all("table")), "table_row_count": sum(len(t.find_all("tr")) for t in main.find_all("table")), "source_cell_count": sum(len(t.find_all(["th", "td"])) for t in main.find_all("table")), "rowspan_anchor_count": sum(_span(c, "rowspan", set()) > 1 for c in main.find_all(["th", "td"])), "colspan_anchor_count": sum(_span(c, "colspan", set()) > 1 for c in main.find_all(["th", "td"])), "merged_cell_anchor_count": sum((_span(c, "rowspan", set()) > 1 or _span(c, "colspan", set()) > 1) for c in main.find_all(["th", "td"])), "link_count": len(main.find_all("a")), "relative_link_count": sum(_relative(a.get("href", "")) for a in main.find_all("a")), "image_count": len(main.find_all("img"))}
    canonical = {"heading_count": sum(x["type"] == "heading" for x in elements), "table_count": len(tables), "table_row_count": sum(len(t["grid"]) for t in tables), "expanded_grid_cell_count": sum(sum(len(row) for row in t["grid"]) for t in tables), "merged_cell_anchor_count": sum(len(t["merged_cells"]) for t in tables), "resolved_link_count": sum(bool(urlparse(url).scheme) for _, url in emitted_urls), "unresolved_relative_link_count": sum(_relative(url) for _, url in emitted_urls), "image_reference_count": len({image["source_node_id"] for image in emitted_images})}
    return {"markdown": "\n\n".join(x["content"] for x in elements if x["content"]), "elements": elements, "tables": tables, "report": {"status": "passed", "engine": "beautifulsoup4_lxml", "source_url": source_url, "main_content": main_content, "html_structure": {"source_metrics": source, "canonical_metrics": canonical}, "warnings": [{"code": code, "message": code} for code in sorted(warnings)]}}


def assess_html_structural_fidelity(structure, tables, elements, chunks, warning_codes, validation=None):
    """Assess source-to-canonical evidence independently of bundle validity."""
    source, canonical = structure["source_metrics"], structure["canonical_metrics"]
    failed = []
    if source["table_count"] != canonical["table_count"]: failed.append("HTML_TABLE_COUNT_MISMATCH")
    if source["merged_cell_anchor_count"] != canonical["merged_cell_anchor_count"]: failed.append("HTML_MERGE_COUNT_MISMATCH")
    if source["heading_count"] and canonical["heading_count"] < source["heading_count"]: failed.append("HEADING_STRUCTURE_WEAK")
    if source["image_count"] > canonical["image_reference_count"]: failed.append("HTML_IMAGE_COUNT_MISMATCH")
    if source["link_count"] > canonical["resolved_link_count"] + canonical["unresolved_relative_link_count"]: failed.append("HTML_LINK_COUNT_MISMATCH")
    table_ids = {table["id"] for table in tables}
    if any(el.get("type") == "table" and el.get("table_id") not in table_ids for el in elements): failed.append("HTML_TABLE_REFERENCE_MISSING")
    if any(not isinstance(row, list) or len(row) != len(table["grid"][0]) for table in tables for row in table.get("grid", []) if table.get("grid")): failed.append("HTML_TABLE_GRID_NOT_RECTANGULAR")
    fatal_warning_codes = {"HTML_TABLE_SPAN_INVALID", "HTML_TABLE_SPAN_OVERLAP", "HTML_TABLE_GRID_IRREGULAR"}
    failed.extend(sorted(fatal_warning_codes.intersection(warning_codes)))
    if validation and validation.get("status") != "passed": failed.append("BUNDLE_VALIDATION_FAILED")
    warnings = sorted(set(warning_codes) - fatal_warning_codes)
    status = "failed" if failed else ("passed_with_warnings" if warnings else "passed")
    return {"status": status, "warning_codes": warnings, "failure_codes": sorted(set(failed)), "metrics": structure}
