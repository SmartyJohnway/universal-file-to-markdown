"""
docx_converter.py
Word -> Markdown with structural (not model-based) fidelity.

Merged-cell handling (v1.1): read directly from OOXML -
  - horizontal merge -> <w:gridSpan w:val="N"/> on the tcPr of a single <w:tc>
  - vertical merge   -> <w:vMerge w:val="restart"/> then <w:vMerge/> (implicit
                        "continue") on the cells below it
Both are read directly, not inferred, so this is exact.

v1.4 additions (Office fidelity):
  - run-level bold/italic rendered as **bold**/*italic*/***both***
  - hyperlinks (via paragraph.iter_inner_content(), which interleaves Run
    and Hyperlink objects in true document order) rendered as Markdown links
  - nested lists: indent level from explicit w:numPr/w:ilvl if present,
    else parsed from the style name's trailing digit (python-docx's own
    "List Bullet 2" / "List Bullet 3" style convention)
  - footnotes/endnotes: extracted directly from word/footnotes.xml /
    word/endnotes.xml (not a first-class python-docx 1.2.0 API), referenced
    inline as [^n] and listed at the end of the document
  - header/footer paragraphs, per section
  - inline image anchoring: an image is inserted as a Markdown reference at
    the point in the text flow where it actually occurs, not just summarized
    in a trailing comment (which was the v1.1 behavior)

v1.3: also returns `elements` (one per paragraph/table block, for
document.json) and `tables` (raw grid per table, for tables/*.csv+*.html).
"""

import re
import os
import zipfile
from xml.etree import ElementTree as ET

from docx import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from common_utils import extract_ooxml_media, extract_ooxml_core_metadata, to_bundle_relative_posix_path

try:
    from docx.text.hyperlink import Hyperlink
    _HAS_HYPERLINK_API = True
except ImportError:
    _HAS_HYPERLINK_API = False

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def convert_docx(path: str, assets_dir: str = None) -> dict:
    doc = Document(path)
    blocks = []
    elements = []
    tables_out = []
    table_count = 0
    merged_cells_found = 0
    nested_tables_found = 0
    image_count = 0
    heading_stack = []

    footnotes = _extract_notes_part(path, "word/footnotes.xml")
    endnotes = _extract_notes_part(path, "word/endnotes.xml")
    used_footnotes = set()
    used_endnotes = set()

    media_saved = extract_ooxml_media(path, assets_dir) if assets_dir else []
    if assets_dir:
        media_saved = [to_bundle_relative_posix_path(os.path.dirname(assets_dir), os.path.join(assets_dir, asset)) for asset in media_saved]
    el_counter = 0
    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            text, refs, img_count_here = _render_paragraph(
                para, footnotes, endnotes, used_footnotes, used_endnotes,
                media_saved, image_count)
            image_count += img_count_here
            if text:
                el_counter += 1
                blocks.append(text)
                is_heading = text.startswith("#")
                is_list_item = bool(re.match(r"^\s*(?:-|1\.)\s+", text))
                level = text.count("#", 0, text.find(" ")) if is_heading else None
                parent_id = heading_stack[-1][1] if heading_stack else None
                if is_heading:
                    heading_stack[:] = [entry for entry in heading_stack if entry[0] < level]
                    parent_id = heading_stack[-1][1] if heading_stack else None
                    heading_stack.append((level, f"p{el_counter:04d}"))
                elements.append({
                    "id": f"p{el_counter:04d}",
                    "parent_id": parent_id,
                    "type": "heading" if is_heading else ("list_item" if is_list_item else "paragraph"),
                    "level": level,
                    "content": text,
                    "engine": "python-docx_custom",
                    "confidence": None,
                    "source_locator": None,
                    "properties": ({"list_level": _list_indent_level(para),
                                    "ordered": bool(re.match(r"^\s*1\.\s+", text))}
                                   if is_list_item else {}),
                })
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            table_md, merges, grid, cells, nested_here = _render_table(table)
            table_count += 1
            merged_cells_found += merges
            nested_tables_found += nested_here
            el_counter += 1
            blocks.append(table_md)
            elements.append({
                "id": f"p{el_counter:04d}",
                "parent_id": heading_stack[-1][1] if heading_stack else None,
                "type": "table",
                "content": table_md,
                "merged_cells": merges,
                "engine": "python-docx_custom",
                "confidence": None,
                "source_locator": {"table_index": table_count},
                "table_id": f"table-{table_count:04d}",
            })
            if grid:
                table_entry = {"id": f"table-{table_count:04d}", "rows": grid,
                                "context": "docx_table",
                                "source_locator": {"table_index": table_count},
                                "engine": "python-docx_custom"}
                if cells:
                    table_entry["cells"] = cells
                tables_out.append(table_entry)

    footnote_section = _render_notes_section("Footnotes", footnotes, used_footnotes)
    endnote_section = _render_notes_section("Endnotes", endnotes, used_endnotes)
    if footnote_section:
        blocks.append(footnote_section)
    if endnote_section:
        blocks.append(endnote_section)

    header_footer_text = _render_headers_footers(doc)
    if header_footer_text:
        blocks.append(header_footer_text)

    metadata = extract_ooxml_core_metadata(path)

    report = {
        "tables_found": table_count,
        "merged_cells_found": merged_cells_found,
        "nested_tables_found": nested_tables_found,
        "media_extracted": len(media_saved),
        "images_anchored_inline": image_count,
        "footnotes_found": len([k for k in footnotes if k not in (-1, 0)]),
        "endnotes_found": len([k for k in endnotes if k not in (-1, 0)]),
        "metadata": metadata,
    }
    if nested_tables_found:
        report["status"] = "passed_with_warnings"
        report["warnings"] = [{"code": "DOCX_NESTED_TABLE_FLATTENED", "count": nested_tables_found,
                               "message": "Nested DOCX tables were projected with explicit cell separators; review before structural use."}]
    return {"markdown": "\n\n".join(blocks), "report": report,
            "elements": elements, "tables": tables_out}


# ---------------------------------------------------------------------------
# Paragraph rendering: run-level bold/italic, hyperlinks, lists, footnotes,
# inline images - all in true document order via iter_inner_content()
# ---------------------------------------------------------------------------

def _render_paragraph(para, footnotes, endnotes, used_footnotes, used_endnotes,
                       media_saved, image_count_so_far):
    style_name = (para.style.name or "").lower()
    img_count_here = 0

    if _HAS_HYPERLINK_API:
        pieces = []
        for item in para.iter_inner_content():
            if isinstance(item, Run):
                pieces.append(_render_run(item))
                ref, kind = _find_note_reference(item)
                if ref is not None:
                    if kind == "footnote":
                        used_footnotes.add(ref)
                        pieces.append(f"[^fn{ref}]")
                    else:
                        used_endnotes.add(ref)
                        pieces.append(f"[^en{ref}]")
                img_name, media_saved, image_count_so_far = _find_inline_image(
                    item, media_saved, image_count_so_far)
                if img_name:
                    img_count_here += 1
                    pieces.append(f"![]({img_name})")
            elif isinstance(item, Hyperlink):
                label = item.text or item.address or ""
                if item.address:
                    pieces.append(f"[{label}]({item.address})")
                else:
                    pieces.append(label)
        text = "".join(pieces).strip()
    else:
        text = para.text.strip()

    if not text:
        return "", [], img_count_here

    if style_name.startswith("heading"):
        try:
            level = int(style_name.replace("heading", "").strip())
        except ValueError:
            level = 1
        level = max(1, min(level, 6))
        return f"{'#' * level} {text}", [], img_count_here

    indent = _list_indent_level(para)
    if "list bullet" in style_name:
        return f"{'  ' * indent}- {text}", [], img_count_here
    if "list number" in style_name:
        return f"{'  ' * indent}1. {text}", [], img_count_here

    return text, [], img_count_here


def _render_run(run: Run) -> str:
    text = run.text
    if not text:
        return ""
    if run.bold and run.italic:
        return f"***{text}***"
    if run.bold:
        return f"**{text}**"
    if run.italic:
        return f"*{text}*"
    return text


def _list_indent_level(para) -> int:
    pPr = para._p.pPr
    if pPr is not None:
        numPr = pPr.find(qn("w:numPr"))
        if numPr is not None:
            ilvl_el = numPr.find(qn("w:ilvl"))
            if ilvl_el is not None:
                try:
                    return int(ilvl_el.get(qn("w:val")))
                except (TypeError, ValueError):
                    pass
    # fallback: python-docx's own "List Bullet 2" / "List Number 3" naming
    m = re.search(r"(\d+)$", para.style.name or "")
    if m:
        return max(0, int(m.group(1)) - 1)
    return 0


def _find_note_reference(run: Run):
    """Detect a w:footnoteReference or w:endnoteReference inside a run.
    Returns (id, 'footnote'|'endnote') or (None, None)."""
    r_el = run._r
    fn = r_el.find(qn("w:footnoteReference"))
    if fn is not None:
        try:
            return int(fn.get(qn("w:id"))), "footnote"
        except (TypeError, ValueError):
            pass
    en = r_el.find(qn("w:endnoteReference"))
    if en is not None:
        try:
            return int(en.get(qn("w:id"))), "endnote"
        except (TypeError, ValueError):
            pass
    return None, None


def _find_inline_image(run: Run, media_saved: list, index_so_far: int):
    """If this run contains a drawing/blip (embedded image), return the
    corresponding already-extracted asset filename by position order.
    This is a positional best-effort match (Nth image drawing in the body
    -> Nth file extracted from word/media/ in archive order) rather than a
    relationship-id-exact match, which is a known simplification - see
    engine_notes.md."""
    r_el = run._r
    has_drawing = r_el.find(qn("w:drawing")) is not None
    if not has_drawing or index_so_far >= len(media_saved):
        return None, media_saved, index_so_far
    return media_saved[index_so_far], media_saved, index_so_far + 1


# ---------------------------------------------------------------------------
# Footnotes / endnotes
# ---------------------------------------------------------------------------

def _extract_notes_part(path: str, part_name: str) -> dict:
    """Read word/footnotes.xml or word/endnotes.xml directly from the zip
    container - not a first-class python-docx 1.2.0 API. Returns
    {id: text}, skipping separator/continuationSeparator placeholder notes."""
    notes = {}
    try:
        with zipfile.ZipFile(path) as z:
            if part_name not in z.namelist():
                return notes
            raw = z.read(part_name)
        root = ET.fromstring(raw)
        for note in root.findall(f"{{{_W_NS}}}footnote") + root.findall(f"{{{_W_NS}}}endnote"):
            note_type = note.get(f"{{{_W_NS}}}type")
            if note_type in ("separator", "continuationSeparator"):
                continue
            note_id = note.get(f"{{{_W_NS}}}id")
            try:
                note_id = int(note_id)
            except (TypeError, ValueError):
                continue
            text = "".join(t.text or "" for t in note.iter(f"{{{_W_NS}}}t")).strip()
            notes[note_id] = text
    except (zipfile.BadZipFile, ET.ParseError):
        pass
    return notes


def _render_notes_section(title: str, notes: dict, used_ids: set) -> str:
    if not used_ids:
        return ""
    prefix = "fn" if title == "Footnotes" else "en"
    lines = [f"## {title}"]
    for note_id in sorted(used_ids):
        text = notes.get(note_id, "(text not found)")
        lines.append(f"[^{prefix}{note_id}]: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Header / footer
# ---------------------------------------------------------------------------

def _render_headers_footers(doc) -> str:
    lines = []
    seen_texts = set()
    for section in doc.sections:
        for part_name, part in (("Header", section.header), ("Footer", section.footer)):
            texts = [p.text.strip() for p in part.paragraphs if p.text.strip()]
            for t in texts:
                if t not in seen_texts:
                    seen_texts.add(t)
                    lines.append(f"<!-- {part_name}: {t} -->")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Table rendering (v1.1/1.2 merged-cell logic, unchanged, now also returns
# the raw grid for tables/*.csv+*.html export)
# ---------------------------------------------------------------------------

def _render_table(table: Table) -> tuple:
    tbl = table._tbl
    rows_xml = tbl.findall(qn("w:tr"))
    grid_cols = len(tbl.findall(qn("w:tblGrid") + "/" + qn("w:gridCol")))
    if grid_cols == 0 or not rows_xml:
        return "", 0, None, None, 0

    cell_grid = [[None] * grid_cols for _ in rows_xml]
    open_vmerge = {}
    merges_found = 0
    any_span = False
    nested_tables_found = 0

    for r_idx, tr in enumerate(rows_xml):
        col_cursor = 0
        for tc in tr.findall(qn("w:tc")):
            while col_cursor < grid_cols and cell_grid[r_idx][col_cursor] is not None:
                col_cursor += 1
            if col_cursor >= grid_cols:
                break

            tc_pr = tc.find(qn("w:tcPr"))
            grid_span = 1
            v_merge_val = None
            if tc_pr is not None:
                gs = tc_pr.find(qn("w:gridSpan"))
                if gs is not None:
                    grid_span = int(gs.get(qn("w:val")))
                vm = tc_pr.find(qn("w:vMerge"))
                if vm is not None:
                    v_merge_val = vm.get(qn("w:val")) or "continue"

            nested_tables = tc.findall(".//" + qn("w:tbl"))
            if nested_tables:
                nested_tables_found += len(nested_tables)
                nested_cells = []
                for nested in nested_tables:
                    for nested_tc in nested.iter(qn("w:tc")):
                        value = "".join(node.text or "" for node in nested_tc.iter(qn("w:t"))).strip()
                        if value:
                            nested_cells.append(value)
                cell_text = "[Nested table: " + " | ".join(nested_cells) + "]"
            else:
                cell_text = "".join(node.text or "" for node in tc.iter(qn("w:t"))).strip()

            if v_merge_val == "continue" and col_cursor in open_vmerge:
                anchor_row = open_vmerge[col_cursor]
                anchor = cell_grid[anchor_row][col_cursor]
                cell_grid[anchor_row][col_cursor] = ("anchor", anchor[1], anchor[2] + 1, anchor[3])
                for i in range(grid_span):
                    if col_cursor + i < grid_cols:
                        cell_grid[r_idx][col_cursor + i] = ("skip",)
                merges_found += 1
                any_span = True
            else:
                if v_merge_val == "restart":
                    open_vmerge[col_cursor] = r_idx
                    merges_found += 1
                    any_span = True
                elif v_merge_val is None:
                    open_vmerge.pop(col_cursor, None)
                if grid_span > 1:
                    merges_found += 1
                    any_span = True
                cell_grid[r_idx][col_cursor] = ("anchor", cell_text, 1, grid_span)
                for i in range(1, grid_span):
                    if col_cursor + i < grid_cols:
                        cell_grid[r_idx][col_cursor + i] = ("skip",)
            col_cursor += grid_span

    for r_idx in range(len(rows_xml)):
        for c_idx in range(grid_cols):
            if cell_grid[r_idx][c_idx] is None:
                cell_grid[r_idx][c_idx] = ("anchor", "", 1, 1)

    raw_grid = [[(cell_grid[r][c][1] if cell_grid[r][c][0] == "anchor" else "")
                 for c in range(grid_cols)] for r in range(len(rows_xml))]

    if not any_span:
        lines = ["| " + " | ".join(_esc(cell_grid[0][c][1]) for c in range(grid_cols)) + " |",
                 "| " + " | ".join(["---"] * grid_cols) + " |"]
        for r in range(1, len(rows_xml)):
            lines.append("| " + " | ".join(_esc(cell_grid[r][c][1]) for c in range(grid_cols)) + " |")
        return "\n".join(lines), merges_found, raw_grid, None, nested_tables_found

    html = ["<table>"]
    cells = []
    for r in range(len(rows_xml)):
        html.append("<tr>")
        for c in range(grid_cols):
            info = cell_grid[r][c]
            if info[0] == "skip":
                continue
            _, text, rowspan, colspan = info
            attrs = ""
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            html.append(f"<td{attrs}>{_html_escape(text)}</td>")
            cells.append({"row": r, "col": c, "value": text,
                          "rowspan": rowspan, "colspan": colspan})
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html), merges_found, raw_grid, cells, nested_tables_found


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc(cell) -> str:
    if cell is None:
        cell = ""
    return str(cell).replace("|", "\\|").replace("\n", "<br>")
