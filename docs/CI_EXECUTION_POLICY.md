# CI execution policy

## Current phase

The repository is in **v1.6.1 release-readiness validation**. Pull-request
validation and `main` push validation are active; release readiness and stable
release work must not rely on manual-only workflows.

## Active validation

- `test` runs on pull requests and `main` pushes with CPython 3.12. The Ubuntu
  runner installs `libgl1` before RapidOCR/OpenCV qualification.
- CodeQL runs on pull requests, `main` pushes, and the weekly schedule.
- Dependency Review runs in real pull-request base/head context. Manual dispatch
  explains that a comparison is not applicable instead of reporting a false pass.
- Markdown-link, license, and metadata validation run on their path-relevant
  pull requests and `main` pushes, and remain manually dispatchable.
- Release gate remains manually dispatchable and runs automatically for `v*`
  tags. Release packaging remains tag-triggered and manually dispatchable.

Recommended required checks are: `test`, `CodeQL`, `Markdown links`, `License
files`, and `Validate repository metadata`. Dependency Review should be made
required only when the repository feature is available and enabled.

## Future iterative development

A future long-running iterative phase may pause automatic CI only through a
separate governance PR. It must restore automatic validation before a
release-readiness or stable-release PR is opened.
