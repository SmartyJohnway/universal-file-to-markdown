import os
import sys
import argparse
import logging
from pathlib import Path
from markitdown import MarkItDown
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter, PdfPipelineOptions
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.models.tesseract_ocr_model import TesseractOcrOptions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def convert_with_docling(input_path, output_path):
    """
    High-quality conversion using Docling, especially for PDF and Excel.
    Docling handles complex layouts and merged cells well.
    """
    logger.info(f"Using Docling to convert {input_path}...")
    
    # Configure pipeline options for better PDF/Table handling
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
    
    converter = DocumentConverter(
        # You can customize allowed formats if needed
    )
    
    result = converter.convert(input_path)
    markdown_content = result.document.export_to_markdown()
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    return True

def convert_with_markitdown(input_path, output_path):
    """
    General purpose conversion using Microsoft MarkItDown.
    Good for Office formats and simple files.
    """
    logger.info(f"Using MarkItDown to convert {input_path}...")
    md = MarkItDown()
    result = md.convert(input_path)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result.text_content)
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Universal File to Markdown Converter")
    parser.add_argument("input", help="Path to the input file")
    parser.add_argument("-o", "--output", help="Path to the output markdown file")
    parser.add_argument("--engine", choices=["auto", "docling", "markitdown"], default="auto", 
                        help="Conversion engine to use (default: auto)")
    
    args = parser.parse_args()
    input_path = Path(args.input)
    
    if not input_path.exists():
        logger.error(f"Input file not found: {input_path}")
        sys.exit(1)
        
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix(".md")
        
    ext = input_path.suffix.lower()
    
    success = False
    
    # Strategy: 
    # 1. Use Docling for PDF, Excel, Word, PPTX (better layout/table handling)
    # 2. Use MarkItDown for others or as fallback
    
    if args.engine == "docling" or (args.engine == "auto" and ext in ['.pdf', '.xlsx', '.xls', '.docx', '.pptx']):
        try:
            success = convert_with_docling(str(input_path), str(output_path))
        except Exception as e:
            logger.warning(f"Docling conversion failed: {e}. Falling back to MarkItDown.")
            if args.engine == "auto":
                success = convert_with_markitdown(str(input_path), str(output_path))
    else:
        success = convert_with_markitdown(str(input_path), str(output_path))
        
    if success:
        logger.info(f"Successfully converted to {output_path}")
    else:
        logger.error("Conversion failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()
