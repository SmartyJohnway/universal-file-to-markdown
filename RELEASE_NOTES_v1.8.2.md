# Universal File to Markdown v1.8.2

> Draft release notes. Finalize the release date and links only after the exact
> `main` commit has passed the Release gate.

## Highlights

- Makes CSV conversion safer for irregular rows and CRLF quoted multiline cells:
  extra fields are retained in deterministic `__extra_N` columns, logical rows
  stay intact in both canonical data and Markdown, and inconsistent widths are
  disclosed with `CSV_INCONSISTENT_COLUMN_COUNT`.
- Makes PDF OCR safer: OCR is probed only when required, native probe failures
  fail closed, mixed PDFs OCR material raster regions, and uncertain OCR tables
  are preserved as text with evidence instead of becoming incorrect canonical tables.
- Improves document fidelity: nested DOCX table surrounding text is retained,
  EML attachment links are Markdown-safe, and chunks consistently record their
  source filename.
- Adds stable pre-parse JSON nesting limits and profile-aware reproducible
  cross-format regression baselines for RapidOCR-only and Tesseract-fallback
  environments.

## Compatibility

Bundle, document, table, and chunk schemas remain at `1.0`. The v1.8.2 changes
are additive correctness and safety improvements; consumers should continue to
inspect `conversion-report.json` and require `bundle_validation.status: passed`.

## Installation and validation

```bash
python -m pip install -r requirements.txt
python scripts/capability_probe.py --json
python scripts/router.py INPUT --output OUTPUT
python scripts/validate_bundle.py OUTPUT
```

## Known boundaries

- OCR tables are canonicalized only with sufficient geometry and token evidence;
  rejected candidates remain readable text with warnings.
- Tesseract is an optional fallback. OCR output can differ by engine profile;
  reproducibility is evaluated against the matching profile baseline.
- Legacy `.doc`, `.xls`, and `.ppt` require conversion to modern OOXML first.

See [CHANGELOG.md](CHANGELOG.md) for the complete change history.
