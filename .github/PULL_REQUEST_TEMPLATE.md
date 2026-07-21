## Summary

Describe the problem and the intended behavior.

## Scope

- Converter or component:
- Canonical contract or schema affected:
- User-visible behavior affected:

## Validation

- [ ] `python scripts/capability_probe.py --json`
- [ ] `python -m pytest tests/ -q`
- [ ] `python -m py_compile scripts/*.py tests/*.py`
- [ ] Added or updated regression tests
- [ ] Validated representative output bundle

## Output and compatibility

- [ ] `document.md` remains backward compatible, or the change is documented
- [ ] Canonical JSON and JSON Schemas remain consistent
- [ ] Chunk and table references validate
- [ ] Warnings and failure states are explicit
- [ ] README, SKILL, capability matrix, or changelog updated where needed

## Privacy and security

- [ ] No confidential document, credential, personal data, generated bundle, or local cache is included
- [ ] Fixtures are synthetic or explicitly redistributable

## Known limitations

List remaining caveats and follow-up work.