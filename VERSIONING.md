# Versioning

`VERSION` is the canonical current skill-version source. The current value,
`1.7.0-rc1`, is a release candidate: it is a target for verification, not a
published stable release. The published stable release remains `1.6.0`; the
target stable release is `1.7.0`.

Skill, document, table, chunk, bundle, and report schema versions are
independent contracts. A skill release alone does not require a schema version
change. Change a schema version only for a compatible-contract decision that
requires consumers to distinguish schemas; change bundle or report versions
only when their respective serialized contracts change.

Release candidates should preserve backward compatibility unless their release
notes state otherwise. Stable-release metadata, tags, and release artifacts are
created only by the release process after qualification.
