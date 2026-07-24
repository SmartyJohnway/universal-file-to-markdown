# AI Review Workflow Guide

This document defines the operating model, trigger criteria, safety contracts, and execution commands for the optional **AI Review Workflow** in `universal-file-to-markdown`.

---

## 1. Purpose & Core Principles

1. **Targeted Enhancement**: AI Review provides LLM-assisted polishing or table formatting for readable markdown projections (`document.md`).
2. **Not Raw Extraction**: AI Review is **not** an AI inspecting raw binary/scanned files from scratch. Extraction is always performed first by deterministic parsers and OCR engines.
3. **Immutable Source Baseline**: The canonical bundle (`document.json`, `tables/*.json`, `chunks.jsonl`, `manifest.json`) is the **immutable source baseline**. AI Review never mutates canonical JSON schemas, element IDs, or source locators.
4. **Readable Projection Only**: AI edits are strictly confined to generating or patching the **readable projection** (`document.md`).
5. **Traceability & Safety**: All AI review requests bind the original file `source_sha256` and `canonical_bundle_fingerprint`. Stale or mismatched reviews are rejected.

---

## 2. Trigger Criteria & Recommendation

The extraction pipeline evaluates structural risk and emits `quality_risk_assessment` in `conversion-report.json`.

AI Review is recommended when:
- High-uncertainty OCR table extraction occurs (`LOW_OCR_CONFIDENCE`, `UNRECONSTRUCTED_SCANNED_TABLE`).
- Merged layout ambiguity is detected (`BOILERPLATE_MAY_BE_INCLUDED`, `MAIN_CONTENT_UNCERTAIN`).
- User explicitly requests AI review refinement.

When AI Review is not needed or disabled, the pipeline directly emits faithful deterministic markdown without invoking an external AI host.

---

## 3. Workflow Steps & Commands

The AI Review workflow follows a 3-step pipeline:

```
+--------------------------+
| 1. prepare_ai_review.py  |  --> Generates ai-review-request.json
+--------------------------+
             |
             v
+--------------------------+
|      Host AI Engine      |  --> Evaluates request & produces ai-review-response.json
+--------------------------+
             |
             v
+--------------------------+
| 2. validate_ai_review.py |  --> Validates response against schema & fingerprints
+--------------------------+
             |
             v
+--------------------------+
| 3. render_readable_...py |  --> Patches document.md (readable projection)
+--------------------------+
```

### Command Sequence

```bash
# Step 1: Generate AI review request package
python scripts/prepare_ai_review.py <bundle_directory>

# Step 2: Validate the response returned by the Host AI
python scripts/validate_ai_review.py <bundle_directory> <ai_review_response.json>

# Step 3: Render the updated readable projection (document.md)
python scripts/render_readable_projection.py <bundle_directory> <ai_review_response.json>
```

---

## 4. Contract & Schema References

- **Request Schema**: `schemas/ai-review-request.schema.json`
- **Response Schema**: `schemas/ai-review-response.schema.json`

### Key Fields in Request (`ai-review-request.json`)
- `schema_version`: `"1.0"`
- `skill_version`: `"1.7.1"`
- `request_id`: e.g. `ai-review-request-a1b2c3d4e5f60718`
- `source_sha256`: SHA-256 of original source file.
- `canonical_bundle_fingerprint`: Cryptographic hash of canonical bundle.
- `targets`: List of review targets (`table` or `element_range`).

---

## 5. Allowed vs. Prohibited Operations

### Allowed Operations
- `replace_table_markdown`: Re-format or re-align markdown tables based on canonical cell data.
- `patch_element_text`: Fix minor OCR typos or formatting glitches in specific readable elements.
- `replace_readable_projection`: Replace full readable markdown projection when extensive structural re-ordering is approved.

### Prohibited Operations
- Modifying canonical JSON (`document.json`, `tables/*.json`, `chunks.jsonl`).
- Altering numbers, dates, currency amounts, or URLs.
- Fabricating untraceable content or facts not present in canonical elements.
- Changing `target_id`, `element_ids`, or `source_locator` mappings.

---

## 6. Table Projection & Target Handling

1. **Table Targets (`target_type: "table"`)**:
   - Primary focus for AI Review.
   - Provides cell contents, bounding boxes, and faithful markdown for complex merged tables.
2. **Element Range Targets (`target_type: "element_range"`)**:
   - Used for text blocks with formatting warnings or OCR uncertainty.
3. **Advisory Targets**:
   - If a target cannot be safely patched without violating constraints, the host AI MUST return an empty patch list or report advisory status rather than making unsafe edits.

---

## 7. Rejection & Failure Behavior

If validation fails (due to schema error, stale fingerprint, fingerprint mismatch, or prohibited operation):
1. `validate_ai_review.py` exits with non-zero status.
2. `render_readable_projection.py` will refuse to apply the review.
3. The bundle retains its original, deterministic `document.md` baseline, ensuring pipeline stability and zero data corruption.
