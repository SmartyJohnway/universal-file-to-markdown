# Support

## Questions and usage help

Use GitHub Discussions when enabled. Otherwise, open a GitHub issue using the question or bug template and include a minimal, non-confidential reproduction.

Before requesting help:

```bash
python scripts/capability_probe.py --json
python -m pytest tests/ -q
```

Also inspect:

- `conversion-report.json`;
- `manifest.json`;
- `references/capability_matrix.md`;
- `references/engine_notes.md`.

## Bug reports

A useful bug report includes:

- skill version and commit SHA;
- Python version and operating system;
- source format and whether the file is digital, scanned, encrypted, malformed, or mixed;
- exact command;
- capability-probe output;
- conversion status, warnings, and error type;
- a synthetic or redistributable fixture where possible.

Do not upload confidential documents, personal email, credentials, or regulated data.

## Scope

Community support is best effort. The project does not provide guaranteed response times, service-level commitments, document-recovery guarantees, legal advice, or paid support through this repository.

Questions about heavy Tier-2 engines such as Docling or MinerU should include the external environment and model configuration, because those engines are not part of the default lightweight runtime.