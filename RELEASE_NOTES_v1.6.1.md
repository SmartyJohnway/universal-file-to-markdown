# Universal File to Markdown v1.6.1

## Summary

v1.6.1 is a reliability patch release for v1.6.0. It improves bundle asset
integrity, conversion-report contracts, and native runtime qualification.

## Fixed

- PPTX broken image links and canonical asset target consistency.
- Asset traversal and missing-target validation.
- Warning/status/report-engine invariants and the empty-output failure contract.

## Runtime hardening

- PyMuPDF child-process import and functional one-page PDF smoke tests.
- RapidOCR/OpenCV child-process import smoke tests.
- Native crash containment plus timeout and signal reporting.
- Required native dependency failure propagation in capability preflight.

## Supported runtime

- **Primary tested:** CPython 3.12.
- **Best effort:** CPython 3.11.
- **Not guaranteed:** CPython 3.13.

## Linux dependency

```bash
sudo apt-get update
sudo apt-get install -y libgl1
```

Other Linux distributions should install the equivalent OpenGL runtime package.

## Schema compatibility

Document, table, and chunk schemas remain **1.0**.

## Upgrade notes

No canonical JSON schema migration is required from v1.6.0. Reconvert PPTX
sources to repair old bundle image paths; existing bundles are not rewritten
automatically. Capability preflight is intentionally stricter: required native
dependencies that cannot import now fail directly.

## Known limitations

- HTML table chunks can still be split across tags.
- OCR table heuristics can still misinterpret `Label: Value` content.
- Chunk locator precision remains limited.
- Python 3.13 is not formally supported.
