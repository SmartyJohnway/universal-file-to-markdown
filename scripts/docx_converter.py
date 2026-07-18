"""
docx_converter.py
Word -> Markdown with structural (not model-based) merged-cell handling.

Word represents merges differently from Excel:
  - horizontal merge -> <w:gridSpan w:val="N"/> on the tcPr of a single <w:tc>
  - vertical merge   -> <w:vMerge w:val="restart"/> on the first cell of the
                        span, then <w:vMerge/> (implicit "continue") on the
                        cells below it

Both are read directly from the OOXML, not inferred, so this is exact.
"""

import os
from docx import Document
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from common_utils import extract_ooxml_media, extract_ooxml_core_metadata


def convert_docx(path: str, assets_dir: str = None) -> dict:
    doc = Document(path)
    blocks = []
    table_count = 0
    merged_cells_found = 0

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            text = _render_paragraph(para)
            if text:
                blocks.append(text)
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            table_md, merges = _render_table(table)
            blocks.append(table_md)
            table_count += 1
            merged_cells_found += merges

    media_saved = []
    if assets_dir:
        media_saved = extract_ooxml_media(path, assets_dir)
        if media_saved:
            blocks.append(
                "\n<!-- embedded media extracted to assets/: "
                + ", ".join(media_saved) + " -->\n"
            )

    metadata = extract_ooxml_core_metadata(path)

    report = {
        "tables_found": table_count,
        "merged_cells_found": merged_cells_found,
        "media_extracted": len(media_saved),
        "metadata": metadata,
    }
    return {"markdown": "\n\n".join(blocks), "report": report}


def _render_paragraph(para: Paragraph) -> str:
    text = para.text.strip()
    if not text:
        return ""
    style_name = (para.style.name or "").lower()
    if style_name.startswith("heading"):
        try:
            level = int(style_name.replace("heading", "").strip())
        except ValueError:
            level = 1
        level = max(1, min(level, 6))
        return f"{'#' * level} {text}"
    if style_name in ("list bullet", "list paragraph") or para.style.name == "List Bullet":
        return f"- {text}"
    if style_name == "list number":
        return f"1. {text}"
    return text


def _render_table(table: Table) -> tuple:
    tbl = table._tbl
    rows_xml = tbl.findall(qn("w:tr"))
    grid_cols = len(tbl.findall(qn("w:tblGrid") + "/" + qn("w:gridCol")))
    if grid_cols == 0 or not rows_xml:
        return "", 0

    # cell_grid[row][col] -> one of:
    #   ("anchor", text, rowspan, colspan)  - render this cell
    #   ("skip",)                           - covered by another cell's span
    cell_grid = [[None] * grid_cols for _ in rows_xml]
    open_vmerge = {}  # col -> anchor_row_idx currently accumulating rowspan
    merges_found = 0
    any_span = False

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

    # fill any untouched cells (ragged rows) as empty anchors
    for r_idx in range(len(rows_xml)):
        for c_idx in range(grid_cols):
            if cell_grid[r_idx][c_idx] is None:
                cell_grid[r_idx][c_idx] = ("anchor", "", 1, 1)

    if not any_span:
        lines = ["| " + " | ".join(_esc(cell_grid[0][c][1]) for c in range(grid_cols)) + " |",
                 "| " + " | ".join(["---"] * grid_cols) + " |"]
        for r in range(1, len(rows_xml)):
            lines.append("| " + " | ".join(_esc(cell_grid[r][c][1]) for c in range(grid_cols)) + " |")
        return "\n".join(lines), merges_found

    html = ["<table>"]
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
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html), merges_found


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _esc(cell) -> str:
    if cell is None:
        cell = ""
    return str(cell).replace("|", "\\|").replace("\n", "<br>")
