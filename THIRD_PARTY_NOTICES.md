# Third-Party Dependencies

Universal File to Markdown is licensed under the Apache License 2.0. Runtime and test dependencies are separate projects distributed under their own licenses.

This repository references dependencies through `requirements.txt`; it does not claim ownership of them or relicense them. When redistributing a bundled environment, executable, container image, or vendored dependency set, review and preserve the applicable upstream licenses and notices.

Key dependency projects include:

- openpyxl
- python-docx
- python-pptx
- pdfplumber
- PyMuPDF
- RapidOCR ONNX Runtime
- pytesseract and the external Tesseract OCR binary
- charset-normalizer
- msoffcrypto-tool
- MarkItDown
- pytest
- jsonschema
- ReportLab
- the optional external Pandoc binary

The authoritative dependency versions are in `requirements.txt`. License metadata can change between releases; downstream distributors are responsible for auditing the exact resolved dependency set they ship.

No model, binary, or source-code license of a dependency is replaced by this project's Apache-2.0 license.