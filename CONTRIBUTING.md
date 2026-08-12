# Contributing

Thank you for helping improve Universal File to Markdown.

## Before contributing

1. Read `README.md`, `SKILL.md`, and `references/capability_matrix.md`.
2. Search existing issues and pull requests before opening a new one.
3. Keep each change focused on one converter, contract, defect, or documentation topic.
4. Do not weaken explicit failure or warning behavior merely to make a conversion appear successful.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/capability_probe.py --json
```

## Required checks

Before submitting a pull request, run:

```bash
python scripts/capability_probe.py --json
python scripts/check_release_consistency.py
python scripts/check_markdown_links.py
python -m pytest tests/ -q
python -m compileall -q scripts tests
```

A release-quality environment must pass the capability probe. Optional system tools may be absent when the affected format path is not under test.
On Windows hosts where the user temp root is inaccessible, give pytest a unique repository-local `--basetemp` path.

## Change requirements

- Add or update regression tests for every behavior change.
- Prefer semantic assertions over full-file snapshots.
- Preserve deterministic output and stable identifiers whenever possible.
- Keep `document.md`, canonical JSON, chunks, table assets, manifest, and quality report mutually consistent.
- Update JSON Schemas when changing a canonical contract.
- Update `README.md`, `README.zh-TW.md`, `SKILL.md`, capability documentation, and `CHANGELOG.md` when user-visible behavior changes.
- Do not commit generated bundles, private documents, credentials, model caches, `.pytest_cache`, `__pycache__`, or virtual environments.

## Pull requests

A pull request should include:

- the problem and intended behavior;
- files and contracts affected;
- tests added or changed;
- commands executed and results;
- known limitations or follow-up work;
- confirmation that no confidential fixture was committed.

Small, reviewable pull requests are preferred over broad refactors.

## Fixtures and privacy

Use synthetic or explicitly redistributable fixtures. Do not commit customer documents, personal email, proprietary Office files, credentials, or regulated data.

## Licensing of contributions

By submitting a contribution, you agree that it may be licensed under the Apache License 2.0, as described in `LICENSE`.
