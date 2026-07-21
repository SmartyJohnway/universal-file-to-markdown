# Governance

Universal File to Markdown is currently maintained by `@SmartyJohnway` under a maintainer-led governance model.

## Decision making

The maintainer has final responsibility for:

- project scope and roadmap;
- release approval and versioning;
- canonical schema compatibility;
- security response;
- contributor and community moderation;
- licensing and redistribution policy.

Technical decisions should be evidence-based and documented through issues, pull requests, tests, schemas, capability notes, or changelog entries.

## Contributions

Contributors retain copyright in their contributions and submit them under Apache License 2.0 according to `CONTRIBUTING.md`.

Acceptance of a contribution does not grant commit, release, or maintainer authority. Repeated high-quality participation may lead to broader review responsibilities at the maintainer's discretion.

## Releases

Releases follow `RELEASING.md` and require:

- a focused release-preparation pull request;
- passing required dependency preflight;
- passing tests and source compilation;
- green required GitHub checks;
- final maintainer approval;
- an exact version tag on the approved commit.

## Schema governance

Canonical schema changes must state whether they are:

- backward-compatible additions;
- behavior clarifications;
- deprecations;
- breaking migrations.

Breaking schema changes require a new schema version and documented migration guidance. Skill version and schema version remain independent.

## Changes to governance

Material governance changes should be made through a public pull request and recorded in the changelog.