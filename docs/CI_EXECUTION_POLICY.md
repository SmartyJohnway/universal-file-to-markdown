# CI execution policy

## Current phase

The **v1.8.1 stable release** is published. Pull requests to `main` and pushes
to `main` run the required automated validation workflows. Developers must
still run the complete local validation suite before every review handoff.

## Manual validation

The release gate remains manually dispatched at explicit release checkpoints.
Dependency Review runs only for pull requests, where GitHub provides the base
and head comparison required for a meaningful result.

## Release packaging

`release-package.yml` remains manually runnable and retains its automatic `v*`
tag trigger. Tagged releases therefore still produce the clean ZIP and
SHA-256 checksum.

## Stable-release controls

Before tagging a stable release, maintainers must confirm that branch
protection requires the active test, CodeQL, dependency review, Markdown-link,
license, and metadata/YAML workflows. The manually dispatched release gate
must pass on the exact candidate commit.
