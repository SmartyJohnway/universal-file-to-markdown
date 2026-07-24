# Changelog

[繁體中文](CHANGELOG.zh-TW.md)

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows Semantic Versioning where practical.

## [1.7.2] - 2026-07-24

### Added

* Native TXT converter (`convert_text.py`) for `.txt`, `.text`, `.log` files.
* Native Markdown converter (`convert_markdown.py`) for `.md`, `.markdown` files.
* Explicit user-requested AI Review CLI (`--force-user-request` and `--target-table` in `prepare_ai_review.py`).
* OCR advisory-only review targets (`target_type: "advisory"`).
* Route-aware optional dependency reporting in `capability_probe.py`.
* Cross-format merged-table AI Review triggers (`table_has_merged_geometry`).

### Fixed

* OOXML merged tables (DOCX, XLSX, PPTX) not triggering AI Review eligibility.
* MarkItDown absence not disclosed by capability probe.
* Incorrect AI Review schema filename in documentation.
* Incorrect readable projection CLI render command example.
* Packaged regression runners failing with unhelpful tracebacks when `tests/` directory is missing.
* Ambiguous Big5/CP950/GB18030 CJK decoding presented with high confidence.

### Changed

* Encoding ambiguity now explicitly reports unresolved status and warns user.
* Agent Skill package excludes source-only regression runners.
* `.txt` and `.md` formats no longer depend on generic MarkItDown fallback.

## [1.7.1] - 2026-07-24

*Unpublished integration milestone. No v1.7.1 tag or GitHub Release was published. Superseded by v1.7.2.*

### Fixed

* Release-state metadata consistency across VERSION, SKILL, README, VERSIONING, PROJECT_STATUS, changelogs, and mirrored schema constraints.
* Broken or package-invalid Markdown links.
* Repository-only test commands being presented as runtime-package commands.
* Incomplete artifact expectations for release-package validation.

### Added

* Dual package profiles: `release` and `agent-skill`.
* Agent Skills-compatible upload ZIP.
* Standalone Agent Skill validator profile.
* AI review workflow documentation in `references/ai_review_workflow.md`.
* Package-profile-specific qualification helpers and tests.
* Extracted-package Markdown link validation.

### Changed

* Release package and Agent Skill package now have separate content boundaries and validation contracts.
* Agent Skill ZIP contains one top-level skill directory (`universal-file-to-markdown/`) with `SKILL.md` at its root.
* Full regression tests are documented as source-repository qualification, not runtime package contents.

## [1.7.0-rc1] - 2026-07-23

This is a release candidate, not a published stable release. The published stable release remains `1.6.0`; `1.7.0` is the target stable release.

### Added

- Reproducible cross-format regression runner, deterministic normalization and fingerprints, Phase 5 workflow coverage, OCR containment cases, and per-case progress reporting.

### Changed

- Qualified RapidOCR `1.4.4` with declared requirement `rapidocr-onnxruntime>=1.4,<2`.
- Documented Python 3.10–3.12 support, Python 3.11 as the primary qualified runtime, and explicit Python 3.13 exclusion.
- Reconciled version, runtime, dependency, format, and capability documentation; schema versions remain independent from the skill version.

### Fixed

- Malformed workflow artifacts no longer crash the unified runner; readable-projection writes and absolute-path validation are portable across platforms.

### Qualification

- RC-head full pytest: 197 passed.
- RC-head unified corpus: pending; it must complete on this release-candidate head before release qualification.
- Historical Phase 6 evidence on the pre-RC main head: 194 tests passed and unified corpus 18/18 passed.

## [Unreleased]

### Added

- Source locator and locator-precision contracts for canonical elements and chunks.
- Chunk-to-element and chunk-to-table provenance references.
- Semantic validation for source locators and provenance references.

### Changed



## [1.6.1-rc2] - 2026-07-22

### Added

- Isolated PyMuPDF import and minimal-PDF functional smoke tests that contain native dependency crashes in child processes.
- Runtime environment and PyMuPDF package-version evidence in capability reports.
- Documented Python and native-dependency compatibility policy.

### Changed

- Pin PyMuPDF to `>=1.26.4,<1.27` for tested-runtime reproducibility; this is not a claim that later releases are universally faulty.

### Fixed

- Correct PPTX Markdown image paths to resolve through the bundle `assets/` directory.
- Validate local Markdown image targets and reject missing, absolute, or escaping paths.
- Enforce consistency between conversion status and warning/error payloads.
- Require a non-empty primary engine for successful conversions.

### Added

- Generic fallback warning for unsupported extensions handled by MarkItDown.
- Regression coverage for Markdown asset usability and report-contract invariants.

### Changed

- Temporarily changed development validation workflows to manual dispatch to conserve GitHub Actions usage during iterative v1.6.1 development.
- Release tag packaging remains automatic.

### Planned

- Expand real-world integration fixtures for encrypted Office files, SmartArt, embedded OLE objects, and complex scanned tables.
- Continue improving format-specific canonical granularity and provenance without breaking schema 1.0 compatibility.

## [1.6.0] - 2026-07-21

### Added

- Canonical document, element, table, and chunk JSON Schemas under `schemas/`.
- Hierarchical canonical document model with a synthetic root and parent/child references.
- Schema-validated `document.json`, `chunks.jsonl`, and canonical table assets.
- Bundle validator covering schema validity, root/tree reachability, cycles, counts, cross-file references, chunk limits, table dimensions, cell bounds, and asset consistency.
- Hard 2,000-character chunk limit with paragraph, line, word, and table-row-aware splitting.
- Repeated Markdown table headers when large tables are split across chunks.
- Locator-rich chunks containing page, sheet, slide, source-file, and element references.
- Shape-level PPTX canonical elements for slides, groups, titles, paragraphs, lists, tables, charts, images, and speaker notes.
- Blank-separated XLSX block elements with chart/image references and cell-range locators.
- Located digital-PDF text blocks and tables with bounding boxes and table-text de-duplication.
- Direct image OCR routing for PNG, JPEG, TIFF, BMP, and WebP.
- Runtime capability probe for required Python dependencies and optional system tools.
- GitHub Actions workflow for dependency installation, capability preflight, tests, and source compilation.
- Release-hardening regression tests, expanding the suite to approximately 65 tests.
- Apache License 2.0, licensing scope, third-party dependency notices, and citation metadata.
- Contribution, governance, security, support, code-of-conduct, maintainer, and authorship documents.
- Issue and pull-request templates, CODEOWNERS, Dependabot, CodeQL, dependency review, metadata validation, Markdown link checking, release gate, and clean release-package workflows.
- Release process, release checklist, release notes draft, repository-settings guidance, and security/dependency policy documentation.

### Changed

- Skill version and data schema version are now explicitly independent: skill `1.6.0`, schema `1.0`.
- Table converters now normalize to a common contract containing dimensions, merge-anchor cells, rectangular grids, engine, confidence, and source locators.
- Standalone HTML table exports preserve rowspan and colspan; CSV exports explicitly flatten merges.
- PPTX bullet handling now resolves explicit `buNone`, `buChar`, and `buAutoNum`, then layout/master inheritance for body-like placeholders; ordinary text boxes default to prose.
- Office preflight now classifies valid OOXML ZIP packages, corrupt containers, and OLE-based encrypted Office files separately.
- Image OCR provenance records the actual RapidOCR or Tesseract path instead of inheriting an unrelated engine label.
- Failed reruns clear known generated artifacts before writing a failure bundle, preventing stale canonical outputs.
- Source locator schemas now constrain page, slide, sheet, shape, table index, and bounding-box types.
- README files now describe Apache-2.0 licensing, release governance, and release-quality checks.

### Fixed

- Corrupt or truncated OOXML files are no longer misreported as password protected.
- Bundle validation now rejects missing roots, invalid root parents, disconnected elements, hierarchy cycles, count mismatches, duplicate chunk IDs, invalid split indexes, incorrect character counts, invalid table dimensions, and out-of-bounds cells.
- Standalone image conversion no longer reports `openpyxl_custom` as its OCR engine.
- Plain PPTX text boxes are no longer converted into false bullet lists.
- Grouped PPTX tables are retained in canonical table output.
- Unsupported SmartArt and embedded OLE content is detected, located, and reported rather than silently dropped.

## [1.5.1] - 2026-07-21

### Added

- SmartArt and embedded OLE presence detection with explicit conversion warnings.
- Common element fields for engine, confidence, and source locator.
- Table-likelihood gating for scanned-PDF table warnings.
- Regression coverage for grouped PPTX tables, merged standalone HTML, schema normalization, and unsupported-content disclosure.

### Changed

- Group-shape rendering now propagates nested table data to table assets.
- Canonical table data includes merge-aware cell geometry for standalone HTML output.
- Scanned PDFs only emit `TABLE_STRUCTURE_UNVERIFIED` when the page exhibits table-like alignment.

### Fixed

- Merged Office tables exported to standalone HTML now preserve rowspan and colspan.
- PPTX nested group tables are no longer omitted from `tables/` output.

### Known issue in the original candidate

- The first v1.5.1 candidate treated paragraphs without explicit PPTX bullet XML as bullets, causing plain text boxes to become lists. This was corrected in v1.6.0.

## [1.5.0] - 2026-07-19

### Added

- Dedicated `python-pptx` converter instead of relying on a generic MarkItDown fallback.
- PPTX merged-table rendering, picture extraction, chart summaries, speaker notes, and group-shape recursion.
- `document.json`, `chunks.jsonl`, and standalone table assets.
- DOCX run-level formatting, hyperlinks, notes, headers, footers, and improved table handling.
- XLSX formula preservation, number/date formatting, comments, hyperlinks, hidden-state metadata, charts, and image references.
- Formal pytest regression suite.

### Changed

- Canonical output evolved from Markdown-only delivery into a traceable AI/RAG bundle.
- Format routing began using magic bytes and OOXML container inspection in addition to file extensions.
- Office encryption detection changed from a boolean result to explicit status handling.

### Fixed

- Short digital PDFs are no longer misrouted to OCR solely because they contain fewer than 50 characters.
- Big5/CP950 CSV files are no longer accepted as plausible UTF-16 output without structural and language checks.
- XLSX formulas without cached values preserve the formula and emit `FORMULA_RESULT_UNAVAILABLE` instead of silently producing blank cells.
- EML attachment filenames are sanitized against traversal and collision risks.

## [1.1.0] - 2026-07-18

### Added

- Initial offline-first multi-format router.
- Custom XLSX conversion with merge-aware HTML tables.
- Custom DOCX conversion with horizontal and vertical merged-cell support.
- PDF digital-text extraction and OCR fallback.
- CSV, JSON, EML, Pandoc, and MarkItDown fallback paths.
- `manifest.json` and `conversion-report.json` output.
- Quality checks for near-empty output, mojibake indicators, OCR confidence, and table uncertainty.

### Design principles established

- Prefer deterministic structural parsers over a single universal converter.
- Preserve merged cells with HTML when Markdown pipe tables are insufficient.
- Use lightweight offline engines in restricted environments.
- Never treat `document.md` alone as proof of successful conversion.

[Unreleased]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
[1.6.0]: https://github.com/SmartyJohnway/universal-file-to-markdown/commit/d4ff2d29a65dce6d0f84780c8d22effe10fe4f5d
[1.5.1]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
[1.5.0]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
[1.1.0]: https://github.com/SmartyJohnway/universal-file-to-markdown/commits/main
