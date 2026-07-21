"""Normalize every converter table to the public table schema v1.0."""

import re


SCHEMA_VERSION = "1.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def normalize_tables(tables: list, source_format: str, default_engine: str = None) -> list:
    normalized = []
    seen = set()
    for ordinal, raw in enumerate(tables, start=1):
        table_id = raw.get("id") or f"table-{ordinal:04d}"
        if not _SAFE_ID.fullmatch(table_id):
            raise ValueError(f"unsafe table id: {table_id}")
        if table_id in seen:
            raise ValueError(f"duplicate table id: {table_id}")
        seen.add(table_id)

        grid = _rectangular_grid(raw.get("grid", raw.get("rows", [])))
        cells = raw.get("cells") or _cells_from_grid(grid)
        canonical_cells = []
        has_merges = False
        for cell in cells:
            row = int(cell.get("row", 0))
            column = int(cell.get("column", cell.get("col", 0)))
            rowspan = int(cell.get("rowspan", 1) or 1)
            colspan = int(cell.get("colspan", 1) or 1)
            has_merges = has_merges or rowspan > 1 or colspan > 1
            canonical_cells.append({
                "row": row,
                "column": column,
                "value": cell.get("value"),
                "rowspan": rowspan,
                "colspan": colspan,
                "is_header": bool(cell.get("is_header", row == 0)),
                "confidence": cell.get("confidence"),
                "source_locator": cell.get("source_locator"),
            })

        locator = dict(raw.get("source_locator") or {})
        context = raw.get("context")
        if context and "context" not in locator:
            locator["context"] = context
        normalized.append({
            "schema_version": SCHEMA_VERSION,
            "id": table_id,
            "source_format": raw.get("source_format", source_format),
            "source_locator": locator,
            "dimensions": {"rows": len(grid), "columns": len(grid[0]) if grid else 0},
            "cells": canonical_cells,
            "grid": grid,
            "confidence": raw.get("confidence"),
            "engine": raw.get("engine") or default_engine,
            "merged_cells_present": has_merges,
            "merged_cells_flattened_in_csv": has_merges,
        })
    return normalized


def _rectangular_grid(rows) -> list:
    rows = [list(row or []) for row in (rows or [])]
    width = max((len(row) for row in rows), default=0)
    return [row + [None] * (width - len(row)) for row in rows]


def _cells_from_grid(grid) -> list:
    return [{"row": r, "column": c, "value": value, "rowspan": 1, "colspan": 1}
            for r, row in enumerate(grid) for c, value in enumerate(row)]
