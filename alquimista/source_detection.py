from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    pass

from .confluence_url import parse_confluence_url


@dataclass(frozen=True)
class DetectedSource:
    """Connection settings inferred from a URL or local path without making a network call."""

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


def _detected(
    registry: Any,
    source_type: str,
    *,
    base_url: str,
    space_key: str = "",
    space_name: str = "",
    root_mode: str = "title",
    root_value: str = "",
) -> DetectedSource:
    descriptor = registry.get(source_type)
    return DetectedSource(
        source_type=source_type,
        display_name=descriptor.display_name,
        base_url=base_url,
        api_name=descriptor.integration_name,
        space_key=space_key,
        space_name=space_name,
        root_mode=root_mode,
        root_value=root_value,
    )


def detect_source_url(
    value: str,
    registry: Any | None = None,
) -> DetectedSource:
    """Detect a supported knowledge platform or local path without network calls."""

    raw = value.strip()
    if registry is None:
        from .connectors.registry import default_registry
        registry = default_registry()


    # 1. Local files and directory paths
    if raw.startswith("file://") or (len(raw) > 2 and raw[1] == ":" and raw[2] in "\\/") or raw.startswith(("\\\\", "/", "./", "../")):
        clean_path = raw.replace("file:///", "").replace("file://", "")
        p = Path(clean_path)
        return _detected(
            registry,
            "local_files",
            base_url=str(p.resolve() if p.exists() else p),
            space_key="root",
            space_name=p.stem,
            root_mode="title",
        )

    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("A URL deve começar com http:// ou https:// e conter um host (ou ser um caminho de arquivo).")
    if parsed.username or parsed.password:
        raise ValueError("Não inclua usuário ou senha na URL.")

    host = (parsed.hostname or "").casefold()
    origin = _origin(parsed)
    path = parsed.path.casefold()

    # Notion
    if host == "api.notion.com" or host.endswith((".notion.so", ".notion.site")):
        root_value = _extract_notion_id(parsed.path)
        return _detected(
            registry,
            "notion_api",
            base_url="https://api.notion.com/v1",
            root_mode="id" if root_value else "title",
            root_value=root_value,
        )

    # SharePoint / MS Graph
    if host == "sharepoint.com" or host.endswith((".sharepoint.com", ".office.com")):
        return _detected(
            registry,
            "sharepoint_graph",
            base_url="https://graph.microsoft.com/v1.0",
            space_key=host,
            root_mode="title",
            root_value="",
        )

    # GitBook
    if host == "api.gitbook.com" or host.endswith((".gitbook.io", ".gitbook.com")):
        parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
        org_id = ""
        space_id = ""
        if "o" in parts and parts.index("o") + 1 < len(parts):
            org_id = parts[parts.index("o") + 1]
        if "s" in parts and parts.index("s") + 1 < len(parts):
            space_id = parts[parts.index("s") + 1]

        space_key = org_id or space_id or _last_path_value(parsed.path)
        return _detected(
            registry,
            "gitbook_api",
            base_url="https://api.gitbook.com/v1",
            space_key=space_key,
            root_mode="space",
            root_value=space_id,
        )

    # Zendesk
    if host.endswith(".zendesk.com") or host == "zendesk.com":
        subdomain = host.split(".", 1)[0] if "." in host else ""
        return _detected(
            registry,
            "zendesk_guide",
            base_url=f"{origin}/api/v2",
            space_key=subdomain,
            root_mode="space",
        )

    # MediaWiki / Wikipedia
    if "wikipedia.org" in host or "mediawiki.org" in host or "wikia.org" in host or "fandom.com" in host or "api.php" in path:
        return _detected(
            registry,
            "mediawiki_api",
            base_url=raw,
            root_mode="title",
        )

    # Confluence
    if host.endswith(".atlassian.net") or "confluence" in host or any(
        marker in path for marker in ("/display/", "/spaces/", "/pages/", "/wiki/")
    ):
        try:
            parsed_confluence = parse_confluence_url(raw)
            root_mode = parsed_confluence.root_mode or ("space" if parsed_confluence.space_key else "title")
            return _detected(
                registry,
                "confluence_rest",
                base_url=parsed_confluence.base_url,
                space_key=parsed_confluence.space_key or "",
                root_mode=root_mode,
                root_value=parsed_confluence.root_value or "",
            )
        except ValueError:
            base_url = f"{origin}/wiki" if host.endswith(".atlassian.net") else origin
            return _detected(
                registry,
                "confluence_rest",
                base_url=base_url,
            )


    # GitHub
    if host == "github.com" or host.endswith(".github.com"):
        parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            branch = "main"
            docs_path = "docs"
            if "tree" in parts and parts.index("tree") + 1 < len(parts):
                idx = parts.index("tree")
                branch = parts[idx + 1]
                docs_path = "/".join(parts[idx + 2 :]) or "docs"
            return _detected(
                registry,
                "github_docs",
                base_url=f"https://github.com/{owner}/{repo}",
                space_key=f"{owner}/{repo}",
                space_name=branch,
                root_mode="title",
                root_value=docs_path,
            )

    # GitLab
    if host == "gitlab.com" or host.endswith(".gitlab.com"):
        parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            return _detected(
                registry,
                "gitlab_docs",
                base_url=origin,
                space_key=f"{owner}/{repo}",
                root_mode="title",
            )

    # Intercom
    if host.endswith(".intercom.com") or host.endswith(".intercom.help") or host == "api.intercom.io":
        return _detected(
            registry,
            "intercom_api",
            base_url="https://api.intercom.io",
            root_mode="title",
        )

    # Salesforce
    if host.endswith(".salesforce.com") or host.endswith(".force.com") or host.endswith(".my.site.com"):
        return _detected(
            registry,
            "salesforce_api",
            base_url=origin,
            root_mode="title",
        )

    # HubSpot
    if host.endswith(".hubspot.com") or host.endswith(".hubapi.com") or host.endswith(".hs-sites.com"):
        return _detected(
            registry,
            "hubspot_api",
            base_url="https://api.hubapi.com",
            root_mode="title",
        )

    # Helpjuice
    if "helpjuice.com" in host or "/helpjuice" in path:
        return _detected(
            registry,
            "helpjuice_api",
            base_url=origin,
            root_mode="space",
        )

    # Guru
    if "getguru.com" in host or "app.getguru.com" in host:
        return _detected(
            registry,
            "guru_api",
            base_url="https://api.getguru.com/api/v1",
            root_mode="title",
        )

    # Slite
    if "slite.com" in host:
        return _detected(
            registry,
            "slite_api",
            base_url="https://api.slite.com/v1",
            root_mode="title",
        )

    # MediaWiki / Wikipedia
    if "wikipedia.org" in host or "mediawiki.org" in host or "wikia.org" in host or "fandom.com" in host or "api.php" in path:
        return _detected(
            registry,
            "mediawiki_api",
            base_url=raw,
            root_mode="title",
        )

    # ReadMe
    if host.endswith(".readme.io") or host.endswith(".readme.com") or "dash.readme.com" in host:
        return _detected(
            registry,
            "readme_api",
            base_url="https://dash.readme.com/api/v1",
            root_mode="space",
        )

    # WordPress
    if host.endswith(".wordpress.com") or "/wp-json" in path or "/wp-content" in path:
        return _detected(
            registry,
            "wordpress_api",
            base_url=origin,
            root_mode="title",
        )

    # Ghost
    if host.endswith(".ghost.io") or "/ghost" in path:
        return _detected(
            registry,
            "ghost_api",
            base_url=origin,
            root_mode="title",
        )

    # Contentful
    if "contentful.com" in host:
        return _detected(
            registry,
            "contentful_api",
            base_url="https://cdn.contentful.com",
            root_mode="space",
        )

    # Sanity
    if "sanity.io" in host:
        return _detected(
            registry,
            "sanity_api",
            base_url=origin,
            root_mode="space",
        )

    # BookStack
    if "/books/" in path or "/api/books" in path or "bookstack" in host:
        book_slug = ""
        parts = [unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
        if "books" in parts and parts.index("books") + 1 < len(parts):
            book_slug = parts[parts.index("books") + 1]
        return _detected(
            registry,
            "bookstack_api",
            base_url=f"{origin}/api",
            space_key=book_slug,
            root_mode="space",
        )

    # Freshdesk
    if "freshdesk.com" in host or "freshservice.com" in host or "/support/solutions" in path:
        return _detected(
            registry,
            "freshdesk_solutions",
            base_url=origin,
            space_key=host.split(".")[0],
            root_mode="space",
        )

    # Outline
    if "getoutline.com" in host or "outline.dev" in host or (host.startswith("kb.") and "/doc/" in path):
        return _detected(
            registry,
            "outline_api",
            base_url=f"{origin}/api",
            root_mode="title",
        )

    # Help Scout
    if "helpscout.net" in host or "helpscoutdocs.com" in host:
        return _detected(
            registry,
            "helpscout_docs",
            base_url="https://docsapi.helpscout.net/v1",
            root_mode="space",
        )

    # Document360
    if "document360.io" in host or "document360.com" in host:
        return _detected(
            registry,
            "document360_api",
            base_url="https://apihub.document360.io/v2",
            root_mode="space",
        )

    # Generic Web and Documentation frameworks
    if parsed.scheme in {"http", "https"}:
        return _detected(registry, "generic_web", base_url=raw, root_mode="id", root_value=raw)

    raise ValueError("A URL deve ser HTTP ou HTTPS pública, ou um caminho de arquivo local.")
