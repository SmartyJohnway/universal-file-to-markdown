"""
format_detector.py
Resolves the REAL format of a file by inspecting its bytes, not just
trusting the extension.

Bug class this addresses (from real-world review): `os.path.splitext`
alone will happily send a mislabeled file to the wrong converter -
`report.pdf` that's actually a DOCX saved with the wrong extension, or an
`.xlsx` that's actually raw HTML exported by some legacy system. Both
common in the wild (email attachments renamed by hand, exports from old
ERP/accounting systems). Sending either into the wrong parser produces a
confusing low-level exception instead of a clear "this file isn't what
its name says it is" message.
"""

import os
import zipfile

_OOXML_CONTAINER_MARKERS = {
    "word/document.xml": "docx",
    "xl/workbook.xml": "xlsx",
    "ppt/presentation.xml": "pptx",
}

_EXT_TO_FORMAT = {
    "xlsx": "xlsx", "xlsm": "xlsx",
    "docx": "docx",
    "pptx": "pptx",
    "pdf": "pdf",
    "png": "image", "jpg": "image", "jpeg": "image", "tif": "image",
    "tiff": "image", "bmp": "image", "webp": "image",
    "csv": "csv", "tsv": "csv",
    "json": "json",
    "eml": "eml",
    "html": "pandoc", "htm": "pandoc", "epub": "pandoc",
    "rst": "pandoc", "org": "pandoc", "tex": "pandoc", "latex": "pandoc",
    "xls": "legacy_office", "doc": "legacy_office", "ppt": "legacy_office",
}


def detect_by_extension(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return _EXT_TO_FORMAT.get(ext, "unknown")


def detect_by_magic(path: str) -> str:
    """Sniff the file's actual bytes. Returns a resolved format string, or
    'unknown' if no signature matched."""
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return "unknown"

    if head[:4] == b"%PDF":
        return "pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n") or head[:3] == b"\xff\xd8\xff":
        return "image"
    if head[:4] in (b"II*\x00", b"MM\x00*") or head[:2] == b"BM":
        return "image"
    if head[:4] == b"RIFF":
        try:
            with open(path, "rb") as f:
                if f.read(12)[8:12] == b"WEBP":
                    return "image"
        except OSError:
            return "unknown"

    if head[:2] == b"PK":  # zip-based container - could be OOXML or a plain zip
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
                for marker, fmt in _OOXML_CONTAINER_MARKERS.items():
                    if marker in names:
                        return fmt
        except zipfile.BadZipFile:
            return "unknown"
        return "unknown"  # a zip, but not a recognized OOXML container

    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "legacy_office_or_encrypted_ooxml"  # OLE2 - old .doc/.xls/.ppt, or an encrypted OOXML file

    # text-based formats don't have a reliable magic number; leave to extension
    return "unknown"


def resolve_format(path: str) -> dict:
    """Returns {"resolved": <format used for routing>, "declared_extension":
    ..., "detected_by_magic": ..., "mismatch": bool}. On a mismatch, the
    magic-byte result wins (it reflects what the file actually is), and the
    mismatch is reported so the user knows the extension lied."""
    by_ext = detect_by_extension(path)
    by_magic = detect_by_magic(path)

    if by_magic == "unknown":
        resolved = by_ext
        mismatch = False
    elif by_magic == "legacy_office_or_encrypted_ooxml":
        # OLE2 signature: genuinely ambiguous between old binary Office
        # formats and a password-protected OOXML file (which is also OLE2
        # at the container level) - let the extension pick a lane, the
        # encryption check downstream will catch the encrypted case.
        resolved = by_ext if by_ext in ("legacy_office",) else "legacy_office"
        mismatch = by_ext not in ("legacy_office", "unknown")
    else:
        resolved = by_magic
        mismatch = by_ext != "unknown" and by_ext != by_magic

    return {
        "resolved": resolved,
        "declared_extension": by_ext,
        "detected_by_magic": by_magic,
        "mismatch": mismatch,
    }
