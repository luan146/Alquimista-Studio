from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..client import ConfluenceClient

if TYPE_CHECKING:
    from ..models import KnowledgeDocument, SourceConfig


def _normalize_ancestors(value: Any) -> list[dict[str, str]]:
    """Keep only the stable ancestor fields required by ``ManifestEntry``."""
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ancestor_id = item.get("id")
        title = item.get("title")
        if isinstance(ancestor_id, (dict, list)) or isinstance(title, (dict, list)):
            continue
        id_text = str(ancestor_id).strip() if ancestor_id is not None else ""
        title_text = str(title).strip() if title is not None else ""
        if not id_text or not title_text:
            continue
        normalized.append({"id": id_text, "title": title_text})
    return normalized


def relative_ancestor_titles(page: dict[str, Any], root_id: str) -> list[str]:
    ancestors = page.get("ancestors", []) or []
    ids = [str(item.get("id", "")) for item in ancestors]
    if root_id in ids:
        ancestors = ancestors[ids.index(root_id) + 1 :]
    elif str(page.get("id")) == root_id:
        ancestors = []
    return [str(item.get("title", "Sem título")) for item in ancestors]


def page_metadata(
    page: dict[str, Any], source: SourceConfig, root: dict[str, Any]
) -> dict[str, Any]:
    root_id = str(root["id"])
    trail = relative_ancestor_titles(page, root_id)
    version_value = page.get("version", {})
    version: dict[str, Any] = version_value if isinstance(version_value, dict) else {}
    space = page.get("space", {}) or root.get("space", {}) or {}
    author_value = version.get("by")
    author_data: dict[str, Any] = author_value if isinstance(author_value, dict) else {}
    labels = [
        str(item.get("name"))
        for item in page.get("metadata", {}).get("labels", {}).get("results", []) or []
        if item.get("name")
    ]
    title = str(page.get("title") or "Sem título")
    path = [str(root.get("title") or source.root_value), *trail, title]
    path = [
        value
        for index, value in enumerate(path)
        if value and (index == 0 or value != path[index - 1])
    ]
    return {
        "source_id": source.id,
        "source_name": source.name,
        "space_key": str(space.get("key") or source.space_key),
        "space_name": str(space.get("name") or source.space_name),
        "root_page_id": root_id,
        "root_title": str(root.get("title") or source.root_value),
        "page_id": str(page["id"]),
        "document_key": f"{source.id}:{page['id']}",
        "title": title,
        "module": trail[0]
        if trail
        else ("Página raiz" if str(page["id"]) == root_id else title),
        "submodule": trail[1] if len(trail) > 1 else "",
        "path": path,
        "ancestors": [
            {"id": str(item.get("id", "")), "title": str(item.get("title", ""))}
            for item in page.get("ancestors", []) or []
        ],
        "source_url": ConfluenceClient.source_url(source.base_url, page),
        "confluence_version": version.get("number"),
        "updated_at": version.get("when"),
        "author": str(author_data.get("displayName") or author_data.get("username") or ""),
        "labels": labels,
    }


def knowledge_document_metadata(
    document: KnowledgeDocument, source: SourceConfig
) -> dict[str, Any]:
    """Convert a normalized document to the manifest's stable metadata shape."""
    path = list(document.path or [document.title])
    container_key = str(document.metadata.get("space_key") or document.container_id)
    updated = document.updated_at.isoformat() if document.updated_at else None
    return {
        "source_id": source.id,
        "source_type": document.source_type,
        "source_name": source.name,
        "container_id": document.container_id,
        "container_type": "space" if document.source_type == "confluence_rest" else "container",
        "container_name": document.container_name,
        "document_id": document.id,
        "parent_id": document.parent_id,
        "page_id": document.id,
        "document_key": f"{source.id}:{document.container_id}:{document.id}",
        "title": document.title,
        "source_url": document.original_url,
        "space_key": container_key,
        "space_name": document.container_name,
        "root_page_id": "",
        "root_title": path[0] if path else document.title,
        "module": path[0] if len(path) > 1 else document.title,
        "submodule": path[1] if len(path) > 2 else "",
        "path": path,
        "ancestors": _normalize_ancestors(document.metadata.get("ancestors")),
        "confluence_version": document.metadata.get("confluence_version"),
        "author": document.metadata.get("author", ""),
        "labels": document.metadata.get("labels", []),
        "updated_at": updated,
        "etag": document.etag or document.metadata.get("etag"),
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "document_type": document.metadata.get("raw_type", "document"),
        "metadata": document.metadata,
    }


__all__ = [
    "_normalize_ancestors",
    "knowledge_document_metadata",
    "page_metadata",
    "relative_ancestor_titles",
]
