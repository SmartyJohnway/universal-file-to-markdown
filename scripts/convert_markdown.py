"""Native Markdown converter for .md and .markdown files without external dependencies."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common_utils import read_text_smart

def convert_markdown_native(input_path: str, encoding_hint: str = None) -> dict:
    """Convert .md or .markdown file directly to Markdown and canonical structures."""
    text, encoding_used, ambiguous, candidates = read_text_smart(input_path, encoding_hint)

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized_text.split("\n")
    line_count = len(lines)

    report = {
        "status": "passed_with_warnings" if ambiguous else "passed",
        "engine": "markdown_native",
        "encoding_used": encoding_used,
        "encoding_ambiguous": ambiguous,
        "encoding_candidates": candidates,
        "encoding_user_selected": bool(encoding_hint),
        "explicit_encoding_recommended": ambiguous,
        "warnings": [],
    }
    if ambiguous:
        report["warnings"].append({
            "code": "ENCODING_AMBIGUOUS",
            "message": "The selected decoding may be semantically wrong even when every character is valid Unicode. Inspect the output and rerun with --encoding when the source may be Big5, CP950, or GB18030.",
        })

    elements = [
        {
            "id": "markdown-block-0001",
            "type": "markdown_block",
            "content": normalized_text,
            "text": normalized_text,
            "engine": "markdown_native",
            "confidence": None,
            "source_locator": {"format": "markdown", "line_start": 1, "line_end": max(1, line_count)},
        }
    ]

    return {
        "markdown": normalized_text,
        "report": report,
        "elements": elements,
        "tables": [],
    }
