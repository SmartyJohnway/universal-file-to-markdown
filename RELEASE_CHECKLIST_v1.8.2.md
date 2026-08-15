# v1.8.2 Release Checklist

This checklist records the release-candidate evidence for `v1.8.2`. It is not
evidence of a published release; tag, GitHub Release, and post-release items
remain pending until the candidate is merged and verified on `main`.

## Candidate evidence

- [x] Full pytest suite completed with zero failures on candidate commit `a5a4e8f`.
- [x] Core cross-format corpus passed in both `rapidocr-only` and
  `rapidocr+tesseract-fallback` profiles, with no baseline or rerun mismatch.
- [x] Release and agent-skill ZIP structures validate; their SHA-256 sidecars match.
- [x] Both ZIPs were installed in clean Python environments and passed the CRLF
  quoted-multiline CSV projection and bundle-validation regression.
- [x] `scripts/check_release_consistency.py` and Markdown link validation pass.

## Before tag and GitHub Release

- [ ] Confirm PR #39 review is approved and all required GitHub checks are green.
- [ ] Merge the candidate to `main` and record the exact merge commit SHA.
- [ ] Dispatch the Release gate on that exact `main` commit.
- [ ] Change release metadata from candidate to stable, set final changelog date,
  and update `CITATION.cff` to v1.8.2 with the actual release date.
- [ ] Re-run the release gate and build both packages from the final release commit.
- [ ] Create annotated tag `v1.8.2`, push it, and verify the tag-triggered package workflow.
- [ ] Create the GitHub Release using `RELEASE_NOTES_v1.8.2.md`.

## Post-release

- [ ] Download and inspect the GitHub source archive.
- [ ] Verify GitHub displays the Apache-2.0 license and citation metadata.
- [ ] Install from a clean environment and rerun capability probe plus core conversion smoke tests.
