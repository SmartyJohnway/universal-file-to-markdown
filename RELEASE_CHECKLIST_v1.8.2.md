# v1.8.2 Release Checklist

This checklist records the release-finalization evidence for `v1.8.2`. Tag,
GitHub Release, and post-release items remain pending until this finalization
commit is merged and verified on `main`.

## Qualification evidence

- [x] Full pytest suite completed with zero failures on candidate commit `a5a4e8f`.
- [x] Core cross-format corpus passed in both `rapidocr-only` and
  `rapidocr+tesseract-fallback` profiles, with no baseline or rerun mismatch.
- [x] Release and agent-skill ZIP structures validate; their SHA-256 sidecars match.
- [x] Both ZIPs were installed in clean Python environments and passed the CRLF
  quoted-multiline CSV projection and bundle-validation regression.
- [x] `scripts/check_release_consistency.py` and Markdown link validation pass.

## Before tag and GitHub Release

- [x] PR #39 was reviewed and merged to `main` as `c76831eec305c63aa298baf95c91dd4ff7a2b70e`.
- [x] Set release metadata to stable, final changelog date, and `CITATION.cff`
  to v1.8.2 with release date 2026-08-15.
- [ ] Confirm this finalization PR review is approved and all required GitHub checks are green.
- [ ] Dispatch the Release gate on the final `main` commit.
- [ ] Re-run the release gate and build both packages from the final release commit.
- [ ] Create annotated tag `v1.8.2`, push it, and verify the tag-triggered package workflow.
- [ ] Create the GitHub Release using `RELEASE_NOTES_v1.8.2.md`.

## Post-release

- [ ] Download and inspect the GitHub source archive.
- [ ] Verify GitHub displays the Apache-2.0 license and citation metadata.
- [ ] Install from a clean environment and rerun capability probe plus core conversion smoke tests.
