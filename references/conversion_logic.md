# Conversion Logic Reference

This document explains the internal logic and engine selection for the `universal-file-to-markdown` skill.

## Engine Comparison

| Feature | Docling | MarkItDown |
|---------|---------|------------|
| **PDF Layout** | Advanced (AI-based) | Basic |
| **OCR** | High Precision (RapidOCR) | Basic (Tesseract/Plugin) |
| **Excel Merged Cells** | Excellent | Poor |
| **Speed** | Moderate | Fast |
| **Breadth** | Core Formats | Very Wide |

## Format Specific Handling

### PDF (.pdf)
- **Engine**: Docling (Primary)
- **OCR**: Enabled by default for scanned pages.
- **Tables**: Docling uses a specialized model to detect and reconstruct table borders and content.

### Excel (.xlsx, .xls)
- **Engine**: Docling (Primary)
- **Merged Cells**: Docling's table-former mode handles merged cells by correctly spanning the content across the logical grid.

### Word (.docx) & PowerPoint (.pptx)
- **Engine**: Docling or MarkItDown.
- **Recommendation**: Use Docling if the document has complex nested tables or multi-column layouts.

### Images (.png, .jpg, .jpeg)
- **Engine**: Docling (OCR mode).
- **Output**: Extracts text from images into Markdown blocks.

### Others (.html, .epub, .msg, .zip)
- **Engine**: MarkItDown.
- **Note**: MarkItDown excels at these specialized or web-native formats.

## Troubleshooting

- **Empty Output**: Check if the file is password protected or corrupted.
- **Garbled Tables**: If Docling fails, try MarkItDown as a fallback, though it may lose merged cell structure.
- **OCR Quality**: Ensure the input image/PDF has sufficient resolution (300 DPI recommended).
