"""
table_export.py
Writes each table a converter detected out as standalone tables/<id>.csv
and tables/<id>.html files, plus an index. This matters for RAG/downstream
tooling that wants to query tabular data directly (e.g. load into pandas)
rather than parse it back out of embedded Markdown/HTML in document.md.

v1.5.1 fix: document.md could show a merged cell correctly (rowspan/colspan
in the embedded HTML/Markdown) while the exact same table's standalone
tables/<id>.html silently flattened it back into a plain grid - every
converter only ever handed this module a flat `rows` grid, discarding the
span geometry it had already computed. Converters that know about merges
(docx/xlsx/pptx) now also pass an optional `cells` list of
{row, col, value, rowspan, colspan} for merge-ANCHOR cells only (spanned/
covered cells are simply absent from `cells`); when present, this module
renders standalone HTML from `cells` instead of re-deriving a flat grid.
`rows` (the flattened grid) is still required and is what CSV always uses,
since CSV has no way to express a span - flattening there is an accepted,
documented limitation, not a bug.
"""

import csv
import io
import json
import os
import re

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def export_tables(tables: list, output_dir: str) -> None:
    if not tables:
        return
    tables_dir = os.path.join(output_dir, "tables")
    os.makedirs(tables_dir, exist_ok=True)

    index = []
    for t in tables:
        tid = t.get("id", "table-0000")
        if not _SAFE_ID.fullmatch(tid):
            raise ValueError(f"unsafe table id: {tid}")
        rows = t.get("grid", t.get("rows", []))
        if not rows:
            continue

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        for row in rows:
            writer.writerow(["" if c is None else c for c in row])
        with open(os.path.join(tables_dir, f"{tid}.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(csv_buf.getvalue())

        cells = t.get("cells")
        with open(os.path.join(tables_dir, f"{tid}.html"), "w", encoding="utf-8") as f:
            if cells:
                f.write(_cells_to_html(cells, rows))
            else:
                f.write(_rows_to_html(rows))

        with open(os.path.join(tables_dir, f"{tid}.json"), "w", encoding="utf-8") as f:
            json.dump(t, f, indent=2, ensure_ascii=False)

        index.append({
            "id": tid,
            "source_format": t.get("source_format"),
            "source_locator": t.get("source_locator"),
            "rows": len(rows),
            "cols": len(rows[0]) if rows else 0,
            "has_merged_cells": bool(t.get("merged_cells_present")),
            "assets": {"csv": f"{tid}.csv", "html": f"{tid}.html", "json": f"{tid}.json"},
        })

    with open(os.path.join(tables_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def _cells_to_html(cells, rows) -> str:
    """Render from an explicit cell list (row, col, value, rowspan,
    colspan) so merge geometry survives into the standalone file. `cells`
    contains one entry per merge-ANCHOR or unmerged cell; cells covered by
    a span simply have no entry and are skipped when building each row."""
    n_rows = len(rows)
    by_row = {}
    for cell in cells:
        by_row.setdefault(cell["row"], []).append(cell)
    for r in by_row:
        by_row[r].sort(key=lambda c: c.get("column", c.get("col", 0)))

    html = ["<table>"]
    for r in range(n_rows):
        html.append("<tr>")
        for cell in by_row.get(r, []):
            attrs = ""
            if cell.get("rowspan", 1) > 1:
                attrs += f' rowspan="{cell["rowspan"]}"'
            if cell.get("colspan", 1) > 1:
                attrs += f' colspan="{cell["colspan"]}"'
            html.append(f"<td{attrs}>{_esc(cell.get('value'))}</td>")
        html.append("</tr>")
    html.append("</table>")
    return "\n".join(html)


def _rows_to_html(rows) -> str:
    html = ["<table>"]
    for row in rows:
        html.append("<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>")
    html.append("</table>")
    return "\n".join(html)


def _esc(v) -> str:
    if v is None:
        return ""
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
