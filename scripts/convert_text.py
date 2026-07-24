"""Native text converter for .txt, .text, and .log files without external dependencies."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common_utils import read_text_smart

def convert_text_native(input_path: str, encoding_hint: str = None) -> dict:
    """Convert .txt, .text, or .log file directly to Markdown and canonical structures."""
    with open(input_path, "rb") as f:
        raw = f.read(4096)
    if b"\x00" in raw and raw.count(b"\x00") > len(raw) * 0.05:
        raise ValueError("binary content cannot be parsed as plain text")

    text, encoding_used, ambiguous, candidates = read_text_smart(input_path, encoding_hint)

    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized_text.split("\n")
    line_count = len(lines)

    report = {
        "status": "passed_with_warnings" if ambiguous else "passed",
        "engine": "text_native",
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
            "id": "text-block-0001",
            "type": "paragraph",
            "content": normalized_text,
            "text": normalized_text,
            "engine": "text_native",
            "confidence": None,
            "source_locator": {"format": "text", "line_start": 1, "line_end": max(1, line_count)},
        }
    ]

    return {
        "markdown": normalized_text,
        "report": report,
        "elements": elements,
        "tables": [],
    }
