"""Turn links between extracted pages into references an AI tool can follow inside the packages."""
from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, unquote_plus, urlsplit

from ..models import ManifestEntry

_LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Page identifiers inside URLs: Confluence (pageId=, /pages/<n>) and Notion (32 hex characters).
_ID_IN_PATH = (re.compile(r"/pages/(\d+)(?:/|$)"), re.compile(r"([0-9a-f]{32})$", re.IGNORECASE))


def _host(url: str) -> str:
    return urlsplit(url).netloc.casefold()


def _normalized(url: str) -> str:
    parts = urlsplit(url)
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.netloc.casefold()}{parts.path.rstrip('/')}{query}"


def _ids(url: str) -> set[str]:
    parts = urlsplit(url)
    found = {value for value in parse_qs(parts.query).get("pageId", [])}
    found.update(match.group(1) for pattern in _ID_IN_PATH if (match := pattern.search(parts.path.rstrip("/"))))
    return {value.replace("-", "").casefold() for value in found}


class PackageLinkIndex:
    """Finds which packaged page a URL points to, by address, page id or ``title=``."""

    def __init__(self, targets: Iterable[tuple[ManifestEntry, str]]) -> None:
        self._by_url: dict[str, tuple[ManifestEntry, str]] = {}
        self._by_id: dict[tuple[str, str], tuple[ManifestEntry, str]] = {}
        self._by_title: dict[tuple[str, str], tuple[ManifestEntry, str]] = {}
        for entry, package in targets:
            if not entry.source_url:
                continue
            target = (entry, package)
            host = _host(entry.source_url)
            self._by_url[_normalized(entry.source_url)] = target
            for document_id in {entry.document_id, entry.page_id, *_ids(entry.source_url)} - {""}:
                self._by_id[(host, document_id.replace("-", "").casefold())] = target
            self._by_title[(host, entry.title.casefold())] = target

    def find(self, url: str) -> tuple[ManifestEntry, str] | None:
        if not url.startswith(("http://", "https://")):
            return None
        if found := self._by_url.get(_normalized(url.split("#", 1)[0])):
            return found
        host = _host(url)
        for document_id in _ids(url):
            if found := self._by_id.get((host, document_id)):
                return found
        titles = parse_qs(urlsplit(url).query).get("title", [])
        return self._by_title.get((host, unquote_plus(titles[0]).casefold())) if titles else None


def link_references(text: str, index: PackageLinkIndex, *, own_key: str, own_package: str) -> str:
    """Replace ``[text](url)`` pointing to another packaged page by ``text (ver «Title» em file)``."""

    def replace(match: re.Match[str]) -> str:
        found = index.find(match.group(2))
        if found is None or found[0].document_key == own_key:
            return match.group(0)
        entry, package = found
        where = "" if package == own_package else f" em {package}"
        label = match.group(1).strip()
        if label.casefold() == entry.title.casefold():
            return f"«{entry.title}»" + (f" ({where.strip()})" if where else "")
        return f"{label} (ver «{entry.title}»{where})"

    return _LINK.sub(replace, text)


__all__ = ["PackageLinkIndex", "link_references"]
