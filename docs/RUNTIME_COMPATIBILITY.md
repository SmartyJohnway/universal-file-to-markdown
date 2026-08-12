# Runtime compatibility

## Supported Python policy

Supported Python is **3.10–3.12**. **Python 3.11** is the primary qualified
runtime for OCR and the cross-format regression suite. **Python 3.13 is not
currently supported.**

## Dependency qualification

`pymupdf>=1.26.4,<1.27` is a reproducibility pin. RapidOCR is required for OCR
routes with declared requirement `rapidocr-onnxruntime>=1.4,<2`; **1.4.4** is
the qualified version. The capability probe validates native imports in an
isolated subprocess so failures are reported rather than crashing the probe.
The default per-child native timeout is 30 seconds and can be changed with
`--native-timeout-seconds`; timeout evidence remains a required-dependency
failure rather than being hidden.

Tesseract and Pandoc are optional system binaries. Pandoc is not required for
the core profile and is required only for Pandoc-enabled routes. Tesseract is
required only when the `pytesseract` fallback is used.

## Native dependencies

On Linux, OpenCV/RapidOCR may require `libGL.so.1`; Debian/Ubuntu users can
install it with `sudo apt-get install -y libgl1`. On Windows, OpenCV may require
the Microsoft Visual C++ runtime. Windows users who use the Tesseract fallback
must install the executable and make it discoverable on `PATH`.
