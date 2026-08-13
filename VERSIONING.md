# Versioning

`VERSION` is the canonical current skill-version source. `1.8.1` is the latest published stable skill version. `v1.7.1` was merged as an unpublished integration milestone (no `v1.7.1` tag or GitHub Release was published) and was superseded by `v1.7.2`.

Skill, document, table, chunk, bundle, and report schema versions are
independent contracts. A skill release alone does not require a schema version
change. Change a schema version only for a compatible-contract decision that
requires consumers to distinguish schemas; change bundle or report versions
only when their respective serialized contracts change.

The `skill_version` `const` in `schemas/ai-review-request.schema.json` is an
intentional mirrored constraint for the producer version. It must remain equal
to `VERSION`; `tests/test_version_consistency.py` enforces that synchronization.

Release candidates should preserve backward compatibility unless their release
notes state otherwise. Stable-release metadata, tags, and release artifacts are
created only by the release process after qualification.
