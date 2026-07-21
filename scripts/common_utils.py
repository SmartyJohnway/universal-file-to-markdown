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

_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_OOXML_REQUIRED_PARTS = {
    ".xlsx": "xl/workbook.xml",
    ".docx": "word/document.xml",
    ".pptx": "ppt/presentation.xml",
}


def check_office_encrypted(path: str) -> str:
    """Return ``encrypted``, ``not_encrypted``, ``corrupt``, or ``unknown``.

    OOXML is a ZIP package, while password-protected modern Office files are
    normally OLE compound containers.  Classify the container first so a
    truncated/fake ZIP can never be reported as password protected.
    """
    extension = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as f:
            signature = f.read(8)
    except OSError:
        return "unknown"

    if signature.startswith(b"PK"):
        try:
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    return "corrupt"
                required_part = _OOXML_REQUIRED_PARTS.get(extension)
                if required_part and required_part not in archive.namelist():
                    return "corrupt"
            return "not_encrypted"
        except (zipfile.BadZipFile, EOFError, OSError):
            return "corrupt"

    if signature == _OLE_SIGNATURE:
        try:
            import msoffcrypto
        except ImportError:
            return "unknown"
        try:
            with open(path, "rb") as f:
                encrypted = msoffcrypto.OfficeFile(f).is_encrypted()
        except Exception:
            return "unknown"
        if encrypted:
            return "encrypted"
        return "corrupt" if extension in _OOXML_REQUIRED_PARTS else "not_encrypted"

    return "corrupt" if extension in _OOXML_REQUIRED_PARTS else "unknown"


def check_pdf_encrypted(path: str) -> str:
    try:
        import fitz
        doc = fitz.open(path)
        return "encrypted" if doc.is_encrypted else "not_encrypted"
    except Exception:
        return "unknown"


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
#
# Bug found in real-world testing: relying solely on charset-normalizer's
# statistical guess misdetected a short Big5-encoded CSV as UTF-16BE. The
# byte sequence happened to decode as *valid* UTF-16BE code points that
# landed inside real Unicode blocks (Cyrillic, Hangul, Yi syllables), so it
# wasn't caught by mojibake/replacement-character checks either - the
# decode succeeded and produced legal-looking-but-wrong Unicode, not
# replacement characters. status was reported "passed" with the file
# silently corrupted.
#
# Fix, in order:
#   1. Try strict UTF-8 first. UTF-8's continuation-byte structure makes
#      an accidental valid decode of non-UTF-8 bytes very unlikely - if it
#      decodes cleanly, trust it and stop.
#   2. If strict UTF-8 fails, try a fixed list of encodings common for
#      Traditional-Chinese/legacy documents and score each successful
#      decode by CHARACTER PLAUSIBILITY (is the result mostly ASCII/CJK/
#      common punctuation, or full of Private-Use-Area/unassigned/
#      unrelated-script characters that a real document wouldn't contain).
#      This is what correctly demotes a UTF-16BE misdecode (which produces
#      implausible scattered scripts) below the real Big5 decode (which
#      produces clean CJK text).
#   3. If two candidates score closely, report the ambiguity explicitly
#      instead of silently picking one.
# ---------------------------------------------------------------------------

_CANDIDATE_ENCODINGS = ["big5", "cp950", "gb18030", "utf-16", "utf-16-be", "shift_jis"]

_PLAUSIBLE_RANGES = (
    (0x0020, 0x007E),   # ASCII printable
    (0x3000, 0x303F),   # CJK punctuation
    (0x4E00, 0x9FFF),   # CJK unified ideographs
    (0x3400, 0x4DBF),   # CJK extension A
    (0xFF00, 0xFFEF),   # halfwidth/fullwidth forms
    (0x2018, 0x201F),   # smart quotes
)


def _is_plausible_char(ch: str) -> bool:
    if ch in ("\n", "\r", "\t"):
        return True
    cp = ord(ch)
    if 0xE000 <= cp <= 0xF8FF:  # Private Use Area - never plausible in real text
        return False
    return any(lo <= cp <= hi for lo, hi in _PLAUSIBLE_RANGES)


def _score_decoded_text(text: str) -> float:
    if not text:
        return 0.0
    sample = text[:2000]
    plausible = sum(1 for c in sample if _is_plausible_char(c))
    bad_control = sum(1 for c in sample if ord(c) < 0x20 and c not in ("\n", "\r", "\t"))
    return (plausible / len(sample)) - 2 * (bad_control / len(sample))


def read_text_smart(path: str, encoding_hint: str = None) -> tuple:
    """Read a text file, auto-detecting encoding. Returns
    (text, encoding_used, ambiguous, candidates_tried) - always 4 values.
    ambiguous=True means the top two candidates scored within 0.15 of each
    other, so the caller should surface that to the user instead of
    silently trusting the top pick."""
    with open(path, "rb") as f:
        raw = f.read()

    if encoding_hint:
        try:
            return raw.decode(encoding_hint), encoding_hint, False, [
                {"encoding": encoding_hint, "score": 1.0, "user_selected": True}]
        except (UnicodeDecodeError, LookupError) as exc:
            raise ValueError(f"requested encoding '{encoding_hint}' cannot decode the file: {exc}") from exc

    # Step 1: strict UTF-8 (with BOM handling) - trust immediately if clean.
    try:
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig"), "utf-8-sig", False, []
        return raw.decode("utf-8"), "utf-8", False, []
    except UnicodeDecodeError:
        pass

    # Step 2: score legacy/CJK candidates by character plausibility.
    scored = []
    for enc in _CANDIDATE_ENCODINGS:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        scored.append((_score_decoded_text(text), enc, text))

    if scored:
        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best_enc, best_text = scored[0]
        ambiguous = len(scored) > 1 and (best_score - scored[1][0]) < 0.15
        candidates = [{"encoding": enc, "score": round(s, 3)} for s, enc, _ in scored]
        return best_text, best_enc, ambiguous, candidates

    # Step 3: last resort - charset-normalizer, then replace-on-error utf-8.
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best is not None:
            return str(best), f"{best.encoding} (fallback detector)", True, []
    except ImportError:
        pass
    return raw.decode("utf-8", errors="replace"), "utf-8 (fallback, undetected)", True, []


# ---------------------------------------------------------------------------
# Native handlers for already-structured formats (don't route these through
# a heavier converter — that only risks losing precision)
# ---------------------------------------------------------------------------

def convert_csv_native(path: str, encoding_hint: str = None) -> dict:
    text, encoding, ambiguous, candidates = read_text_smart(path, encoding_hint)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample)
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        markdown = f"<!-- source_encoding: {encoding} -->\n"
        return {"markdown": markdown, "encoding": encoding, "ambiguous": ambiguous,
                "candidates": candidates, "rows": []}

    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(_escape_pipe(c) for c in header) + " |",
             "| " + " | ".join(["---"] * len(header)) + " |"]
    padded_rows = [header]
    for row in body:
        row = row + [""] * (len(header) - len(row))
        row = row[:len(header)]
        padded_rows.append(row)
        lines.append("| " + " | ".join(_escape_pipe(c) for c in row) + " |")
    note = f"<!-- source_encoding: {encoding} -->\n"
    markdown = note + "\n".join(lines) + "\n"
    return {"markdown": markdown, "encoding": encoding, "ambiguous": ambiguous,
            "candidates": candidates, "rows": padded_rows}


def convert_json_native(path: str, encoding_hint: str = None) -> dict:
    text, encoding, ambiguous, candidates = read_text_smart(path, encoding_hint)
    valid = True
    try:
        parsed = json.loads(text)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        valid = False
        pretty = text  # not valid JSON; show as-is rather than fail
    return {"markdown": "```json\n" + pretty + "\n```\n", "encoding": encoding,
            "ambiguous": ambiguous, "candidates": candidates, "valid": valid}


def convert_eml_native(path: str) -> dict:
    """Returns dict with markdown body + list of extracted attachment bytes,
    using only the Python standard library.

    Security note (found in real-world review): an attachment's declared
    filename comes from the email itself, which is attacker-controlled. A
    filename like "../../outside.bin" must never be joined directly onto
    an output directory path. Sanitization happens here, at the point the
    untrusted name is captured, not left to the caller to remember."""
    with open(path, "rb") as f:
        msg = message_from_binary_file(f, policy=email_default_policy)

    header_lines = []
    for h in ("From", "To", "Cc", "Subject", "Date"):
        if msg[h]:
            header_lines.append(f"**{h}:** {msg[h]}")

    body_text = ""
    html_body = ""
    attachments = []
    seen_names = set()
    if msg.is_multipart():
        for part in msg.walk():
            disp = part.get_content_disposition()
            if disp == "attachment":
                raw_name = part.get_filename() or "attachment.bin"
                safe_name = _sanitize_filename(raw_name, seen_names)
                seen_names.add(safe_name)
                attachments.append({
                    "filename": safe_name,
                    "original_filename": raw_name,
                    "content": part.get_payload(decode=True),
                })
            elif part.get_content_type() == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            elif part.get_content_type() == "text/html" and not html_body:
                payload = part.get_payload(decode=True)
                if payload:
                    html_body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body_text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")

    if not body_text and html_body:
        # HTML-only email (no text/plain alternative) - strip tags with a
        # simple regex rather than silently dropping the whole body, which
        # is what happened before this fix.
        body_text = re.sub(r"<[^>]+>", " ", html_body)
        body_text = re.sub(r"\s+", " ", body_text).strip()
        body_text += "\n\n<!-- rendered from text/html part; no text/plain alternative was present -->"

    md = "\n".join(header_lines) + "\n\n---\n\n" + body_text
    return {"markdown": md, "attachments": attachments}


def _sanitize_filename(name: str, seen: set) -> str:
    base = os.path.basename(name.replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]", "_", base) or "attachment.bin"
    base = base[:200]
    candidate = base
    stem, ext = os.path.splitext(base)
    counter = 1
    while candidate in seen:
        candidate = f"{stem}_{counter}{ext}"
        counter += 1
    return candidate


def _escape_pipe(cell: str) -> str:
    return str(cell).replace("|", "\\|").replace("\n", "<br>")
