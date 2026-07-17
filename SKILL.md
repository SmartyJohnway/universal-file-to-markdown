---
name: universal-file-to-markdown
description: Convert various file formats (PDF, Excel, Word, PPTX, etc.) to high-quality Markdown. Specializes in handling PDF OCR and Excel merged cells using advanced engines like Docling and MarkItDown.
---

# Universal File to Markdown

This skill provides a robust workflow for converting diverse document formats into AI-ready Markdown, with a focus on preserving structure in complex files.

## Capabilities

- **High-Fidelity PDF Parsing**: Uses Docling for advanced layout analysis, preserving reading order and tables.
- **OCR Support**: Automatically performs OCR on scanned PDFs and images.
- **Excel Merged Cells**: Handles complex spreadsheet structures, including merged cells, by converting them to clean Markdown tables.
- **Multi-Format Support**: Handles `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.html`, `.epub`, `.msg`, and more.
- **Engine Fallback**: Automatically switches between Docling (high precision) and MarkItDown (high speed/breadth) based on file type and success.

## Usage Guide

### Core Conversion Workflow

When a user provides a file to be converted to Markdown, follow these steps:

1. **Identify the File Type**: Check the extension and nature of the file (e.g., scanned PDF vs. digital PDF).
2. **Select the Engine**:
   - Use **Docling** for: PDFs (especially with tables/OCR needs), Excel (merged cells), Word, and PPTX.
   - Use **MarkItDown** for: Simple Office files, HTML, EPUB, and as a fast fallback.
3. **Execute Conversion**: Run the bundled conversion script.

### Command Line Interface

Use the provided script for most tasks:

```bash
python3 /home/ubuntu/skills/universal-file-to-markdown/scripts/convert_to_md.py <input_file> -o <output_file>
```

Options:
- `--engine [docling|markitdown|auto]`: Force a specific engine (default: `auto`).

## Best Practices

### Handling PDF OCR
- For scanned documents, ensure the `do_ocr` flag is enabled in the conversion script (enabled by default in the bundled script).
- If text is garbled, try forcing the `docling` engine which has superior layout detection.

### Handling Excel Merged Cells
- Excel files with merged cells are notoriously difficult for simple parsers.
- The `docling` engine is specifically optimized to reconstruct the logical table structure from merged cells. Always prefer `docling` for `.xlsx` files.

### Post-Processing
- After conversion, verify the table structures in the output Markdown.
- If a table is too wide, consider splitting it or using a more specialized tool if requested.

## Bundled Resources

- `scripts/convert_to_md.py`: The main entry point for conversions.
- `references/conversion_logic.md`: Detailed explanation of how different formats are handled.
