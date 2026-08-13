# v1.8.1 Release Checklist

This is the release audit record for tag `v1.8.1`
(`026222ab1b7d6137ab509477e4e02ad961dfa9dd`). Checked items have recorded
v1.8.1 evidence; unchecked post-release inspections were not separately
recorded and must not be implied by the release tag.

## Repository

- [x] `LICENSE` contains Apache License 2.0.
- [x] README files identify Apache-2.0.
- [x] Changelog files contain final v1.8.1 notes and date.
- [x] `CITATION.cff` version and release date are correct.
- [x] `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, and `CODE_OF_CONDUCT.md` are present.
- [x] Issue templates, PR template, CODEOWNERS, Dependabot, and release-note configuration are present.
- [x] No generated bundle, cache, credential, confidential fixture, or personal document was included in the tagged release package.

## Technical gate

- [x] `python -m pip install -r requirements.txt`
- [x] `python scripts/capability_probe.py --json` passes.
- [x] `python scripts/check_release_consistency.py` passes.
- [x] `python scripts/check_markdown_links.py` passes.
- [x] `python -m pytest tests/ -q` passes with zero failures and zero errors.
- [x] `python -m compileall -q scripts tests` passes.
- [x] GitHub Actions test workflow is green.
- [x] CodeQL is green or has no unresolved release-blocking alert.
- [x] Manual release-gate workflow is green.

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

- [x] Merge release-preparation PR into `main`.
- [x] Confirm exact release commit SHA.
- [x] Create annotated tag `v1.8.1` on the verified commit.
- [x] Manually dispatch the Release gate on the exact candidate commit.
- [x] Run the tag-triggered package workflow and attach its validated artifacts.
- [x] Create GitHub Release using `RELEASE_NOTES_v1.8.1.md`.
- [ ] Download and inspect the GitHub source archive.
- [ ] Verify GitHub displays the Apache-2.0 license and citation metadata.
- [x] Verify README links and changelog links.
