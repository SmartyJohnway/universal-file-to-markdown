"""Small deterministic parser for inline Markdown image references we emit."""
from dataclasses import dataclass
from urllib.parse import unquote
import re

_IMAGE_RE = re.compile(r"(?<!\\)!\[[^\]]*\]\(([^\n]*)\)")

@dataclass(frozen=True)
class MarkdownReference:
    kind: str
    raw_target: str
    normalized_target: str
    line_number: int


def _target(destination: str) -> str:
    destination = destination.strip()
    if destination.startswith("<"):
        end = destination.find(">")
        if end != -1:
            return destination[1:end]
    # Converter output uses unescaped destinations; optional titles follow
    # whitespace. This deliberately does not parse arbitrary CommonMark.
    return re.split(r"\s+(?=[\"'])", destination, maxsplit=1)[0].strip()


def parse_markdown_image_references(markdown: str) -> list[MarkdownReference]:
    references = []
    for match in _IMAGE_RE.finditer(markdown):
        raw = _target(match.group(1))
        references.append(MarkdownReference(
            kind="image", raw_target=raw, normalized_target=unquote(raw),
            line_number=markdown.count("\n", 0, match.start()) + 1,
        ))
    return references
