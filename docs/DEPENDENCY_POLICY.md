# Dependency Policy

## Principles

- Prefer maintained, well-scoped dependencies with clear licenses.
- Keep runtime dependencies lightweight and compatible with offline operation.
- Avoid unpinned major-version upgrades in release branches.
- Treat OCR engines, Office parsers, PDF parsers, and generic fallback engines as security-sensitive.

## Updates

Dependabot may open grouped pull requests. Each dependency update should:

- review upstream release notes and license changes;
- run the required capability probe and test suite;
- exercise the affected converter path;
- confirm canonical output and warnings remain stable;
- document behavior changes in the changelog when user-visible.

## Locking and reproducibility

`requirements.txt` currently constrains compatible version ranges. Release artifacts should record the resolved environment when reproducibility is material. A future release may add a generated lock file without replacing the human-maintained compatibility constraints.

## Licensing

Dependencies retain their upstream licenses. See `THIRD_PARTY_NOTICES.md`. Redistributors of bundled environments are responsible for preserving applicable license and notice files.