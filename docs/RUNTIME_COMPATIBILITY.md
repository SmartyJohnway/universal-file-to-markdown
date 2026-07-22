# Runtime compatibility

## Supported Python policy

The primary tested interpreter is **CPython 3.12**. CPython 3.11 is supported
on a best-effort basis. CPython 3.13 is not currently guaranteed until the
complete dependency set has been clean-installed and qualified there.

This policy is intentionally specific to the dependency stack, not a claim
that a failure observed in one host applies to every runtime. A native failure
is described as a **runtime-specific native dependency compatibility issue**.

## Dependency qualification

`pymupdf>=1.26.4,<1.27` is a reproducibility pin for the tested runtime
matrix. It does not assert that PyMuPDF 1.27 or later is generally defective.
The capability probe discovers the module without importing it, then uses
isolated subprocesses to import `fitz` and create/reopen a one-page PDF.
Native crashes and timeouts are reported by the parent process as required
dependency failures.

RapidOCR is a required Python package for the OCR routes. Its qualification is
also performed in a subprocess and imports both RapidOCR and OpenCV, so a
missing native library such as `libGL.so.1` fails preflight rather than being
mistaken for availability. RapidOCR package availability (including any Python
3.13 installation limitation) remains separate from PyMuPDF qualification.
Tesseract and Pandoc are optional system binaries: their absence is reported
but does not fail capability preflight.
