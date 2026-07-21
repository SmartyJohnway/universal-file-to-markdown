# v1.6.0 Release Checklist

## Repository

- [ ] `LICENSE` contains Apache License 2.0.
- [ ] README files identify Apache-2.0.
- [ ] Changelog files contain final v1.6.0 notes and date.
- [ ] `CITATION.cff` version and release date are correct.
- [ ] `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, and `CODE_OF_CONDUCT.md` are present.
- [ ] Issue templates, PR template, CODEOWNERS, Dependabot, and release-note configuration are present.
- [ ] No generated bundle, cache, credential, confidential fixture, or personal document is committed.

## Technical gate

- [ ] `python -m pip install -r requirements.txt`
- [ ] `python scripts/capability_probe.py --json` passes.
- [ ] `python -m pytest tests/ -q` passes with zero failures and zero errors.
- [ ] `python -m py_compile scripts/*.py tests/*.py` passes.
- [ ] GitHub Actions test workflow is green.
- [ ] CodeQL is green or has no unresolved release-blocking alert.
- [ ] Manual release-gate workflow is green.

## Smoke conversions

- [ ] Short digital PDF.
- [ ] Scanned PDF or standalone image OCR.
- [ ] Big5/CP950 CSV.
- [ ] DOCX merged table.
- [ ] XLSX formulas with and without cached values.
- [ ] PPTX prose, bullets, merged table, chart, image, and notes.
- [ ] Corrupt OOXML returns `corrupt_or_invalid_office_container`.
- [ ] Encrypted Office returns `password_protected`.
- [ ] Every successful smoke bundle passes `scripts/validate_bundle.py`.

## Release

- [ ] Merge release-preparation PR into `main`.
- [ ] Confirm exact release commit SHA.
- [ ] Create annotated tag `v1.6.0` on the verified commit.
- [ ] Run tag-triggered release gate.
- [ ] Create GitHub Release using `RELEASE_NOTES_v1.6.0.md`.
- [ ] Download and inspect the GitHub source archive.
- [ ] Verify GitHub displays the Apache-2.0 license and citation metadata.
- [ ] Verify README links and changelog links.
