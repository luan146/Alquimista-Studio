from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from .confluence_url import parse_confluence_url


@dataclass(frozen=True)
class DetectedSource:
    """Connection settings inferred from a URL without making a network call."""

    source_type: str
    display_name: str
    base_url: str
    api_name: str
    space_key: str = ""
    space_name: str = ""
    root_mode: str = "title"
    root_value: str = ""


def _origin(parsed) -> str:
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _last_path_value(path: str) -> str:
    values = [unquote(part).strip() for part in path.split("/") if part.strip()]
    return values[-1] if values else ""


def _extract_notion_id(path: str) -> str:
    # Notion IDs are 32-char hex string (sometimes formatted with hyphens: 8-4-4-4-12)
    match = re.search(r"([0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12})", path)
    if match:
        return match.group(1).replace("-", "")
    return _last_path_value(path)


def detect_source_url(value: str) -> DetectedSource:
    """Detect a supported knowledge platform from its public URL shape.

    Detection is deliberately local. Credentials are not requested and no API
    is contacted here; the connector performs authentication and discovery in
    the following connection/pages steps.
    """

    raw = value.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A URL deve começar com http:// ou https:// e conter um host.")
    if parsed.username or parsed.password:
        raise ValueError("Não inclua usuário ou senha na URL.")

    host = (parsed.hostname or "").casefold()
    origin = _origin(parsed)
    path = parsed.path.casefold()

    if host == "api.notion.com" or host.endswith(".notion.so") or host.endswith(".notion.site"):
        root_value = _extract_notion_id(parsed.path)
        return DetectedSource(
            source_type="notion_api",
            display_name="Notion",
            base_url="https://api.notion.com/v1",
            api_name="API oficial do Notion",
            root_mode="id" if root_value else "title",
            root_value=root_value,
        )

    if "sharepoint.com" in host or host.endswith(".office.com"):
        return DetectedSource(
            source_type="sharepoint_graph",
            display_name="SharePoint",
            base_url="https://graph.microsoft.com/v1.0",
            api_name="Microsoft Graph",
            space_key=host,
            root_mode="title",
            root_value="",
        )

    if host == "api.gitbook.com" or host.endswith(".gitbook.io") or host.endswith(".gitbook.com"):
        parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
        org_id = ""
        space_id = ""
        if "o" in parts and parts.index("o") + 1 < len(parts):
            org_id = parts[parts.index("o") + 1]
        if "s" in parts and parts.index("s") + 1 < len(parts):
            space_id = parts[parts.index("s") + 1]
        
        space_key = org_id or space_id or _last_path_value(parsed.path)
        return DetectedSource(
            source_type="gitbook_api",
            display_name="GitBook",
            base_url="https://api.gitbook.com/v1",
            api_name="API REST oficial do GitBook",
            space_key=space_key,
            root_mode="space",
            root_value=space_id,
        )

    if host.endswith(".zendesk.com") or host == "zendesk.com":
        subdomain = host.split(".", 1)[0] if "." in host else ""
        return DetectedSource(
            source_type="zendesk_guide",
            display_name="Zendesk",
            base_url=f"{origin}/api/v2",
            api_name="Help Center API do Zendesk",
            space_key=subdomain,
            root_mode="space",
        )

    if host.endswith(".atlassian.net") or "confluence" in host or any(
        marker in path for marker in ("/display/", "/spaces/", "/pages/", "/wiki/")
    ):
        try:
            parsed_confluence = parse_confluence_url(raw)
            root_mode = parsed_confluence.root_mode or ("space" if parsed_confluence.space_key else "title")
            return DetectedSource(
                source_type="confluence_rest",
                display_name="Confluence",
                base_url=parsed_confluence.base_url,
                api_name="API REST oficial do Confluence",
                space_key=parsed_confluence.space_key or "",
                root_mode=root_mode,
                root_value=parsed_confluence.root_value or "",
            )
        except ValueError:
            base_url = f"{origin}/wiki" if host.endswith(".atlassian.net") else origin
            return DetectedSource(
                source_type="confluence_rest",
                display_name="Confluence",
                base_url=base_url,
                api_name="API REST oficial do Confluence",
            )

    raise ValueError(
        "Não foi possível identificar a plataforma por esta URL. "
        "Use um endereço do Confluence, Zendesk, Notion, SharePoint ou GitBook."
    )
