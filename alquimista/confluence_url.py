from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote_plus, urlparse


@dataclass(frozen=True)
class ParsedConfluenceUrl:
    base_url: str
    space_key: str = ""
    root_mode: str = ""
    root_value: str = ""
    title: str = ""
    page_id: str = ""
    entire_space: bool = False


def parse_confluence_url(value: str) -> ParsedConfluenceUrl:
    """Extract safe project fields from common Confluence page URLs."""
    raw_str = value.strip()
    parsed = urlparse(raw_str)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Informe uma URL completa iniciada por http:// ou https://.")

    parts = [unquote_plus(part) for part in parsed.path.split("/") if part]
    base_path = "/wiki" if parts and parts[0].casefold() == "wiki" else ""
    base_url = f"{parsed.scheme}://{parsed.netloc}{base_path}"
    query = {key.casefold(): values for key, values in parse_qs(parsed.query).items()}
    page_id = (query.get("pageid") or query.get("page_id") or [""])[0].strip()
    space_key = (query.get("spacekey") or query.get("space") or query.get("key") or [""])[0].strip()
    title = ""

    lowered = [part.casefold() for part in parts]
    if "display" in lowered:
        index = lowered.index("display")
        if len(parts) > index + 1 and not space_key:
            space_key = parts[index + 1]
        if len(parts) > index + 2:
            title = " ".join(parts[index + 2 :]).replace("+", " ").replace("-", " ").strip()

    if "spaces" in lowered:
        index = lowered.index("spaces")
        if len(parts) > index + 1 and not space_key:
            space_key = parts[index + 1]

    if "pages" in lowered:
        index = lowered.index("pages")
        if len(parts) > index + 1:
            candidate = parts[index + 1]
            if candidate.isdigit() and not page_id:
                page_id = candidate
                if len(parts) > index + 2 and not title:
                    title = parts[index + 2].replace("+", " ").replace("-", " ").strip()
            elif candidate.casefold() in {"edit-v2", "reorder", "edit"} and len(parts) > index + 2:
                if parts[index + 2].isdigit() and not page_id:
                    page_id = parts[index + 2]

    # Regex fallback for any 7+ digit page ID in path if not yet found
    if not page_id:
        match = re.search(r"/pages/(\d{6,15})", parsed.path)
        if match:
            page_id = match.group(1)

    if page_id:
        return ParsedConfluenceUrl(
            base_url=base_url,
            space_key=space_key,
            root_mode="id",
            root_value=page_id,
            title=title,
            page_id=page_id,
            entire_space=False,
        )
    if title:
        return ParsedConfluenceUrl(
            base_url=base_url,
            space_key=space_key,
            root_mode="title",
            root_value=title,
            title=title,
        )
    if space_key:
        return ParsedConfluenceUrl(
            base_url=base_url,
            space_key=space_key,
            root_mode="space",
            entire_space=False,
        )
    return ParsedConfluenceUrl(
        base_url=base_url,
        space_key=space_key,
        entire_space=False,
    )
