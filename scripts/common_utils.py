"""
common_utils.py
Shared, dependency-light helpers used by every format-specific converter.

Design principle: everything in this file is deterministic structural
parsing (zipfile, XML, stdlib) or a single small offline library
(charset-normalizer). Nothing here downloads a model or calls the network.
"""

import csv
import io
import json
import os
import re
import zipfile
from email import message_from_binary_file
from email.policy import default as email_default_policy
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Encryption / password-protection detection
# ---------------------------------------------------------------------------

def check_office_encrypted(path: str) -> bool:
    """Return True if a .docx/.xlsx/.pptx/.doc/.xls/.ppt file is password protected.

    Encrypted OOXML files are actually OLE2 compound files (not valid zips),
    so a failed zip open is itself a strong signal. msoffcrypto-tool gives a
    definitive answer when installed; we fall back to the zip-open heuristic
    if it isn't available.
    """
    try:
        import msoffcrypto
        with open(path, "rb") as f:
            try:
                office_file = msoffcrypto.OfficeFile(f)
                return bool(office_file.is_encrypted())
            except Exception:
                return False
    except ImportError:
        # Fallback heuristic: a real OOXML file must open as a zip.
        try:
            with zipfile.ZipFile(path):
                return False
        except zipfile.BadZipFile:
            return True


def check_pdf_encrypted(path: str) -> bool:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path)
        return doc.is_encrypted
    except Exception:
        return False


# ---------------------------------------------------------------------------
# OOXML (docx/xlsx/pptx) media + metadata extraction
# ---------------------------------------------------------------------------

_MEDIA_PREFIXES = ("word/media/", "xl/media/", "ppt/media/")

_CORE_NS = {
    "cp": "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
    "dc": "http://purl.org/dc/elements/1.1/",
    "dcterms": "http://purl.org/dc/terms/",
}


def extract_ooxml_media(path: str, out_dir: str) -> list:
    """Pull every embedded image/media file out of a docx/xlsx/pptx zip
    container and save it under out_dir. Returns a list of relative
    asset paths (for referencing from the generated Markdown).
    """
    saved = []
    os.makedirs(out_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.startswith(_MEDIA_PREFIXES):
                    base = os.path.basename(name)
                    dest = os.path.join(out_dir, base)
                    # avoid collisions if multiple sheets/slides reuse names
                    counter = 1
                    stem, ext = os.path.splitext(dest)
                    while os.path.exists(dest):
                        dest = f"{stem}_{counter}{ext}"
                        counter += 1
                    with z.open(name) as src, open(dest, "wb") as dst:
                        dst.write(src.read())
                    saved.append(os.path.relpath(dest, out_dir))
    except zipfile.BadZipFile:
        pass  # encrypted or non-OOXML; caller should have already checked
    return saved


def extract_ooxml_core_metadata(path: str) -> dict:
    """Read docProps/core.xml (author, created/modified time, title) —
    pure XML parse, no extra dependency."""
    meta = {}
    try:
        with zipfile.ZipFile(path) as z:
            if "docProps/core.xml" not in z.namelist():
                return meta
            raw = z.read("docProps/core.xml")
        root = ET.fromstring(raw)
        fields = {
            "title": "dc:title",
            "creator": "dc:creator",
            "last_modified_by": "cp:lastModifiedBy",
            "created": "dcterms:created",
            "modified": "dcterms:modified",
        }
        for key, tag in fields.items():
            prefix, local = tag.split(":")
            el = root.find(f"{{{_CORE_NS[prefix]}}}{local}")
            if el is not None and el.text:
                meta[key] = el.text
    except Exception:
        pass
    return meta


# ---------------------------------------------------------------------------
# Encoding detection for legacy plain-text / CSV files (Big5, GBK, etc.)
# ---------------------------------------------------------------------------

def read_text_smart(path: str) -> tuple:
    """Read a text file, auto-detecting encoding. Returns (text, encoding_used).
    Defaults to utf-8 only if detection genuinely can't decide; never silently
    mangles CJK legacy-encoded files by assuming utf-8 first.
    """
    with open(path, "rb") as f:
        raw = f.read()
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            return str(best), best.encoding
    except ImportError:
        pass
    # last-resort fallback
    return raw.decode("utf-8", errors="replace"), "utf-8 (fallback, undetected)"


# ---------------------------------------------------------------------------
# Native handlers for already-structured formats (don't route these through
# a heavier converter — that only risks losing precision)
# ---------------------------------------------------------------------------

def convert_csv_native(path: str) -> str:
    text, encoding = read_text_smart(path)
    # sniff delimiter (comma vs tab vs semicolon)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return ""
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(_escape_pipe(c) for c in header) + " |",
             "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in body:
        row = row + [""] * (len(header) - len(row))  # pad ragged rows
        lines.append("| " + " | ".join(_escape_pipe(c) for c in row[:len(header)]) + " |")
    note = f"<!-- source_encoding: {encoding} -->\n"
    return note + "\n".join(lines) + "\n"


def convert_json_native(path: str) -> str:
    text, _ = read_text_smart(path)
    try:
        parsed = json.loads(text)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pretty = text  # not valid JSON; show as-is rather than fail
    return "```json\n" + pretty + "\n```\n"


def convert_eml_native(path: str) -> dict:
    """Returns dict with markdown body + list of extracted attachment bytes,
    using only the Python standard library."""
    with open(path, "rb") as f:
        msg = message_from_binary_file(f, policy=email_default_policy)

    header_lines = []
    for h in ("From", "To", "Cc", "Subject", "Date"):
        if msg[h]:
            header_lines.append(f"**{h}:** {msg[h]}")

    body_text = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disp = part.get_content_disposition()
            if disp == "attachment":
                attachments.append({
                    "filename": part.get_filename() or "attachment.bin",
                    "content": part.get_payload(decode=True),
                })
            elif part.get_content_type() == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body_text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    md = "\n".join(header_lines) + "\n\n---\n\n" + body_text
    return {"markdown": md, "attachments": attachments}


def _escape_pipe(cell: str) -> str:
    return str(cell).replace("|", "\\|").replace("\n", "<br>")
