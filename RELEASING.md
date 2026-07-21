# Release Process

This document defines the release gate for Universal File to Markdown.

## 1. Prepare the release branch

- Update `SKILL.md`, both README files, both changelogs, and `CITATION.cff`.
- Confirm `SKILL_VERSION` in `scripts/router.py`.
- Confirm schema versions in `schemas/` remain compatible or document migrations.
- Remove local caches and generated bundles.

## 2. Validate the environment

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/capability_probe.py --json
```

The required dependency probe must pass in the release environment.

## 3. Run the release gate

```bash
python -m pytest tests/ -q
python -m py_compile scripts/*.py tests/*.py
```

Also run representative smoke conversions for:

- short digital PDF;
- scanned PDF or raster image OCR;
- Big5/CP950 CSV;
- DOCX merged table;
- XLSX formula with and without cached value;
- PPTX prose, bullet list, merged table, chart, image, and notes;
- malformed OOXML and encrypted Office classification.

For every successful smoke conversion, run:

```bash
python scripts/validate_bundle.py OUTPUT_DIRECTORY
```

## 4. Review release artifacts

Confirm:

- `conversion-report.json` and `bundle_validation.status` are correct;
- no confidential fixtures, generated bundles, caches, credentials, or personal data are committed;
- Apache-2.0 `LICENSE` is present;
- changelog date and version are final;
- README links are valid;
- GitHub Actions is green on the release commit.

## 5. Merge and tag

1. Merge the release-preparation pull request into `main`.
2. Verify CI on the resulting `main` commit.
3. Create an annotated tag named `vX.Y.Z` on that exact commit.
4. Push the tag.
5. Create a GitHub Release from the tag.

Recommended tag message:

```text
Universal File to Markdown vX.Y.Z
```

## 6. GitHub Release notes

Release notes should contain:

- major capabilities;
- important correctness and security fixes;
- supported formats and boundaries;
- schema compatibility;
- installation and validation commands;
- known limitations;
- link to the full changelog.

## 7. Post-release verification

- Download the GitHub source archive and inspect its contents.
- Install from a clean virtual environment.
- Run capability probe and the full test suite.
- Verify the tag, release title, citation metadata, and license display correctly.
- Move completed changelog entries out of `Unreleased` only after the release commit is final.
