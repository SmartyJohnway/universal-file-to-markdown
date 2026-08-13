# Layout and association contract

This reference defines the additive v1.8 metadata carried by canonical PDF and
PPTX elements. Document, table, and chunk schema versions remain `1.0` because
existing required fields and meanings are unchanged and all new fields are
optional under the existing `properties` extension point.

## Layout hints

Located elements may contain:

```json
{
  "properties": {
    "layout": {
      "reading_order": 3,
      "region_id": "page-0001-region-02",
      "region_type": "column",
      "column_index": 1,
      "layout_zone": "body_left",
      "order_confidence": 0.9,
      "order_method": "deterministic_xycut_v1",
      "source_extraction_index": 4
    }
  }
}
```

`reading_order` is one-based and unique among siblings that declare it. It is
the order used to emit both `document.md` and the converter's flat canonical
element list. It is not a global element ordinal and does not override the
parent/child hierarchy.

`column_index` is `0` for spanning, unlocated, note, or ordinary single-flow
regions and starts at `1` for detected body columns. `order_confidence`
describes the deterministic rule's geometric support; it is not OCR confidence
and is not a probability that the author intended that flow.

For located digital-PDF text, `source_extraction_index` is the one-based
per-page position of the first contributing text line encountered in PyMuPDF's
parser traversal. It preserves separate extraction evidence when deterministic
geometry changes `reading_order`. It is not a visual order, semantic order, or
claim about author intent; filtered table text can leave intentional gaps, and
tables or geometry-less fallback text do not declare this field.

Current methods are:

- `deterministic_geometry_v1`: single-flow PDF bbox order;
- `deterministic_xycut_v1`: strong PDF column separation with banded spanning regions;
- `placeholder_role_geometry_v1`: ordinary PPTX role then geometry order;
- `placeholder_role_columns_v1`: strong PPTX side-by-side column flow;
- `geometry_top_left_ambiguous_v1`: overlapping PPTX fallback;
- `stable_source_order_fallback_v1`: material shape without usable geometry;
- `ooxml_notes_relationship_v1`: speaker notes placed after slide content.

Consumers must continue to surface `READING_ORDER_UNCERTAIN` and
`VISUAL_FLOW_AMBIGUOUS`; a populated plan does not suppress those warnings.

## Association edges

Strong-evidence relationships are stored on both endpoints:

```json
{
  "relation": "caption_of",
  "target_id": "page-0001-table-001",
  "confidence": 0.95,
  "evidence": [
    "caption_prefix",
    "vertical_proximity",
    "horizontal_alignment"
  ],
  "method": "deterministic_rule_v1"
}
```

Supported reciprocal pairs are:

| Forward | Reverse | Evidence gate |
|---|---|---|
| `caption_of` | `captioned_by` | table/figure prefix, nearest compatible object, bounded vertical gap, at least 50% horizontal alignment |
| `note_for` | `has_note` | native OOXML slide-notes relationship |

Caption rules never link ordinary prose that merely contains words such as
"table" or "figure". If the prefix, compatible target type, bbox, distance, or
alignment evidence is absent, no edge is created. Bundle validation rejects
self-references, missing targets, missing reciprocal edges, malformed evidence,
and duplicate sibling reading-order values.

## Known limits

- PDF column detection requires enough separated blocks in both columns.
- A narrow isolated side note is intentionally not promoted to a full column.
- Tables or figures without bbox evidence cannot receive geometric captions.
- Overlapping slides, dashboards, arrows, and other visual narratives can
  require a human or downstream multimodal agent.
- Associations describe source-supported structure only; they do not copy or
  rewrite canonical content.
