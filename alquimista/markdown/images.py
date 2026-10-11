"""Turn Markdown/HTML images into plain text an AI tool can read without the original site."""
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse

ImageReader = Callable[[str], str | None]

_URL = r"<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?"
_LINKED_IMAGE = re.compile(r"\[!\[([^\]]*)\]\(\s*" + _URL + r"\s*\)\]\([^)]*\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(\s*" + _URL + r"\s*\)")
_HTML_IMAGE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HTML_ATTRIBUTE = r"""\b{name}\s*=\s*(?:"([^"]*)"|'([^']*)')"""
_MAX_IMAGE_TEXT = 1500


def _file_name(url: str) -> str:
    if url.startswith("data:"):
        return "imagem embutida"
    return unquote(PurePosixPath(urlparse(url).path).name) or "imagem"


def _describe(alt: str, url: str, read: ImageReader | None) -> str:
    label = " ".join(alt.split()) or _file_name(url)
    found = " ".join((read(url) or "").split()) if read else ""
    if found:
        return f"[Imagem: {label} — texto na imagem: {found[:_MAX_IMAGE_TEXT]}]"
    return f"[Imagem: {label}]"


def _html_attribute(tag: str, name: str) -> str:
    match = re.search(_HTML_ATTRIBUTE.format(name=name), tag, re.IGNORECASE)
    return (match.group(1) or match.group(2) or "") if match else ""


def images_as_text(markdown: str, read: ImageReader | None = None) -> str:
    """Replace every image by ``[Imagem: description]``; ``read`` may add the text inside it."""
    markdown = _LINKED_IMAGE.sub(lambda m: _describe(m.group(1), m.group(2), read), markdown)
    markdown = _IMAGE.sub(lambda m: _describe(m.group(1), m.group(2), read), markdown)
    return _HTML_IMAGE.sub(
        lambda m: _describe(_html_attribute(m.group(0), "alt"), _html_attribute(m.group(0), "src"), read),
        markdown,
    )


__all__ = ["ImageReader", "images_as_text"]
