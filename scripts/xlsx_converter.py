"""
xlsx_converter.py
Deterministic Excel -> Markdown/HTML conversion with full merged-cell
fidelity. No AI model involved: openpyxl exposes merged ranges directly,
so reconstruction is exact, not inferred.

Rule of thumb:
  - a sheet with NO merged cells -> clean Markdown pipe table
  - a sheet WITH merged cells    -> HTML <table> with real rowspan/colspan
    (GFM pipe tables cannot express spans; forcing them in loses structure)
"""

import os
import openpyxl


def convert_xlsx(path: str, assets_dir: str = None) -> dict:
    wb_values = openpyxl.load_workbook(path, data_only=True)   # computed values
    wb_formulas = openpyxl.load_workbook(path, data_only=False)  # raw formulas

    sections = []
    report = {
        "sheets": [],
        "total_merged_ranges": 0,
        "merged_ranges_rendered": 0,
        "hidden_sheets": [],
        "hidden_rows_or_columns_present": False,
    }

    for ws_name in wb_values.sheetnames:
        ws = wb_values[ws_name]
        ws_f = wb_formulas[ws_name]

        if ws.sheet_state != "visible":
            report["hidden_sheets"].append(ws_name)

        merged_ranges = list(ws.merged_cells.ranges)
        report["total_merged_ranges"] += len(merged_ranges)

        hidden_row = any(dim.hidden for dim in ws.row_dimensions.values())
        hidden_col = any(dim.hidden for dim in ws.column_dimensions.values())
        if hidden_row or hidden_col:
            report["hidden_rows_or_columns_present"] = True

        if merged_ranges:
            table_md, rendered = _render_html_table(ws, ws_f, merged_ranges)
            report["merged_ranges_rendered"] += rendered
            engine = "html_table_with_span"
        else:
            table_md = _render_pipe_table(ws)
            engine = "markdown_pipe_table"

        sections.append(f"## Sheet: {ws_name}\n\n{table_md}\n")
        report["sheets"].append({
            "name": ws_name,
            "merged_ranges": len(merged_ranges),
            "engine": engine,
            "hidden": ws.sheet_state != "visible",
        })

    markdown = "\n".join(sections)
    return {"markdown": markdown, "report": report}


def _render_pipe_table(ws) -> str:
    rows = list(ws.iter_rows(values_only=True))
    # drop fully-empty trailing rows/cols to avoid noise
    rows = [r for r in rows if any(c is not None for c in r)]
    if not rows:
        return "_(empty sheet)_"
    max_cols = max(len(r) for r in rows)
    header = rows[0]
    lines = ["| " + " | ".join(_cell_str(c) for c in _pad(header, max_cols)) + " |",
             "| " + " | ".join(["---"] * max_cols) + " |"]
    for r in rows[1:]:
        lines.append("| " + " | ".join(_cell_str(c) for c in _pad(r, max_cols)) + " |")
    return "\n".join(lines)


def _render_html_table(ws, ws_f, merged_ranges) -> tuple:
    """Render as HTML table, expanding merged ranges into real
    rowspan/colspan attributes on the anchor (top-left) cell and
    skipping the other cells the merge covers."""
    merge_lookup = {}  # (row, col) -> ("anchor"|"skip", rowspan, colspan)
    rendered = 0
    for mr in merged_ranges:
        min_r, min_c, max_r, max_c = mr.min_row, mr.min_col, mr.max_row, mr.max_col
        rowspan = max_r - min_r + 1
        colspan = max_c - min_c + 1
        merge_lookup[(min_r, min_c)] = ("anchor", rowspan, colspan)
        for r in range(min_r, max_r + 1):
            for c in range(min_c, max_c + 1):
                if (r, c) != (min_r, min_c):
                    merge_lookup[(r, c)] = ("skip", 0, 0)
        rendered += 1

    max_row = ws.max_row
    max_col = ws.max_column
    html = ["<table>"]
    for r in range(1, max_row + 1):
        html.append("<tr>")
        for c in range(1, max_col + 1):
            info = merge_lookup.get((r, c))
            if info and info[0] == "skip":
                continue
            value = ws.cell(row=r, column=c).value
            cell_text = "" if value is None else str(value)
            if info and info[0] == "anchor":
                _, rowspan, colspan = info
                attrs = ""
                if rowspan > 1:
                    attrs += f' rowspan="{rowspan}"'
                if colspan > 1:
                    attrs += f' colspan="{colspan}"'
                html.append(f"<td{attrs}>{_html_escape(cell_text)}</td>")
            else:
                html.append(f"<td>{_html_escape(cell_text)}</td>")
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html), rendered


def _pad(row, n):
    row = list(row)
    return row + [None] * (n - len(row))


def _cell_str(v) -> str:
    if v is None:
        return ""
    return str(v).replace("|", "\\|").replace("\n", "<br>")


def _html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
