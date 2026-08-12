# Chunk consumer contract

Version `1.0` of this additive contract is emitted by skill version `1.8.1`.
The serialized chunk schema remains `1.0`: older consumers may ignore every
field described here, and bundles whose legacy chunks omit
`consumer_contract_version` remain valid.

## Two text views

`text` is the authoritative source-derived chunk projection. It is never
shortened to make room for context and retains the existing 2,000-character
hard maximum.

`embedding_text` is a deterministic consumer convenience view:

```text
embedding_text = context_prefix + text
```

It also has a 2,000-character hard maximum. Context is added one complete
metadata line at a time only while budget remains. If source text consumes the
budget, `context_prefix` is empty and `context_truncated` is `true`. Consumers
that do not want metadata in embeddings should continue to use `text`.

## Reference fields

| Field | Meaning |
|---|---|
| `ancestor_element_ids` | Ordered non-document ancestors of the chunk elements |
| `section_element_id` | One shared nearest heading, otherwise `null` |
| `unit_element_id` | One shared nearest page, slide, or sheet, otherwise `null` |
| `related_element_ids` | Ordered targets of strong canonical association edges |
| `relationships` | ID-only copies of association edges whose sources are in the chunk |
| `relation_types` | Ordered unique relationship types |
| `layout_region_ids` | Ordered unique canonical layout region IDs |
| `layout_zones` | Ordered unique layout zones |
| `layout_order_methods` | Ordered unique deterministic ordering methods |
| `column_indexes` | Ordered unique zero-based column indexes |
| `context_element_ids` | Ordered union of ancestor and related IDs |

These fields do not copy the content of a related table, figure, caption, or
note. A consumer must resolve an ID against `document.json` when it needs that
evidence. This prevents hidden fact duplication and keeps canonical evidence as
the only source of truth.

`relationships` contains `source_element_id`, `relation`,
`target_element_id`, `confidence`, `evidence`, and `method`. Bundle validation
requires every value to match the source element's canonical association.

## Budget and validation fields

- `context_policy` is `source_text_priority_v1`.
- `context_char_count` equals the length of `context_prefix`.
- `embedding_char_count` equals the length of `embedding_text`.
- `context_truncated` reports that at least one eligible complete context line
  could not fit.
- Both source and embedding views are limited to 2,000 characters.

Bundle validation independently derives every reference/layout field from
`document.json`, reconstructs the expected prefix, and rejects stale,
fabricated, missing, or over-budget projections.

## Consumer scorecard

Score one or more validated bundles without changing them:

```bash
python scripts/score_chunk_context.py bundle-a bundle-b
```

The JSON scorecard reports bundle validation, contract/context/locator
coverage, duplicate exact-text chunks, length distributions, truncated-context
counts, relationship coverage, and hard-limit violations. These are operational
signals, not a claim that retrieval relevance or semantic understanding has
been solved. Retrieval hit-rate evaluation still requires consumer queries and
ground-truth judgments outside the extraction core.

## Consumer rules

1. Validate the bundle before indexing it.
2. Use `text` for evidence-preserving display and quotation.
3. Use `embedding_text` only as a retrieval projection; resolve returned IDs
   back to canonical elements.
4. Do not infer a semantic relationship from physical proximity when no
   canonical association exists.
5. Treat `context_truncated` as budget disclosure, not source loss.
6. Deduplicate by source SHA, element IDs, and locator before deduplicating by
   text alone.
