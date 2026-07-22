# CI execution policy

## Current phase

The repository is in **v1.6.1 iterative development**. Automatic push and
pull-request validation is temporarily disabled to conserve GitHub Actions
minutes. Developers must run the complete local/Codex-sandbox validation suite
before every review handoff.

## Manual validation

Development workflows are available through `workflow_dispatch` and should be
run only at explicit review and release gates. Dependency Review cannot produce
a meaningful comparison without pull-request context; its manual workflow
reports that it is deferred to final release validation rather than claiming a
successful review.

## Release packaging

`release-package.yml` remains manually runnable and retains its automatic `v*`
tag trigger. Tagged releases therefore still produce the clean ZIP and
SHA-256 checksum.

## Restoration before v1.6.1 stable

Restore automatic validation in a dedicated release-readiness PR before the
stable release, including: test, CodeQL, dependency review, Markdown links,
license check, metadata/YAML validation, and release gate. Maintainers must
also confirm required-status-check branch protection matches the active trigger
policy; otherwise GitHub may wait indefinitely for checks that are no longer
automatically created.
