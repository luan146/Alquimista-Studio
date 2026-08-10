"""Pure data transformations used by the document tree UI.

This module deliberately has no Qt dependency.  ``MainWindow`` remains the
compatibility facade, while normalization and visibility rules can be tested
without constructing a window.
"""

from __future__ import annotations

from typing import Any

from ..models import AuthMode, SourceConfig


def page_container_id(source: SourceConfig, page: dict[str, Any]) -> str:
    return str(
        page.get("_container_id")
        or (page.get("space") or {}).get("key")
        or source.space_key
        or "__default__"
    )


def tree_pages(data: dict[str, Any], container_id: str | None = None) -> list[dict[str, Any]]:
    pages_by_container = data.get("pages_by_container") or {}
    if pages_by_container:
        if container_id is not None:
            return _deduplicate_pages(pages_by_container.get(str(container_id), []) or [], str(container_id))
        result: list[dict[str, Any]] = []
        for key, pages in pages_by_container.items():
            result.extend(_deduplicate_pages(pages or [], str(key)))
        return _deduplicate_pages(result)
    pages = list(data.get("pages", []) or [])
    if container_id is None:
        return _deduplicate_pages(pages)
    return _deduplicate_pages(
        [
            page
            for page in pages
            if str(page.get("_container_id") or (page.get("space") or {}).get("key") or "__default__")
            == str(container_id)
        ],
        str(container_id),
    )


def _deduplicate_pages(
    pages: list[dict[str, Any]], container_id: str | None = None
) -> list[dict[str, Any]]:
    """Keep one metadata row per remote document in a container."""

    result: list[dict[str, Any]] = []
    positions: dict[tuple[str, str], int] = {}
    for raw in pages:
        if not isinstance(raw, dict):
            continue
        page = dict(raw)
        page_id = str(page.get("id") or "")
        if not page_id:
            continue
        effective_container = str(
            container_id
            or page.get("_container_id")
            or (page.get("space") or {}).get("key")
            or "__default__"
        )
        page.setdefault("_container_id", effective_container)
        key = (effective_container, page_id)
        existing_index = positions.get(key)
        if existing_index is None:
            positions[key] = len(result)
            result.append(page)
            continue
        existing = result[existing_index]
        for field, value in page.items():
            if value not in (None, "", [], {}):
                existing.setdefault(field, value)
    return result


def page_parent_id(page: dict[str, Any], page_ids: set[str]) -> str | None:
    """Return the known parent id, using the provider's ancestor fallback."""
    parent_id = str(page.get("parent_id") or "")
    if parent_id not in page_ids:
        ancestors = page.get("ancestors") or []
        ancestor_id = str(ancestors[-1].get("id") or "") if ancestors else ""
        parent_id = ancestor_id if ancestor_id in page_ids else ""
    if parent_id == str(page.get("id") or ""):
        parent_id = ""
    return parent_id or None


def parent_ids_in_list(pages: list[dict[str, Any]]) -> set[str]:
    """Ids that act as parent of another page within *pages*."""
    page_ids = {str(page.get("id", "")) for page in pages if page.get("id")}
    parents: set[str] = set()
    for page in pages:
        parent_id = page_parent_id(page, page_ids)
        if parent_id:
            parents.add(parent_id)
    return parents


def ordered_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep provider order while placing known parents before their children."""
    page_list = list(pages)
    if any(page.get("provider_ordered") is True for page in page_list):
        return page_list
    page_ids = {str(page.get("id", "")) for page in page_list if page.get("id")}
    children: dict[str, list[int]] = {}
    parents: list[str | None] = []

    for index, page in enumerate(page_list):
        parent_id = page_parent_id(page, page_ids)
        parents.append(parent_id)
        if parent_id:
            children.setdefault(parent_id, []).append(index)

    ordered: list[dict[str, Any]] = []
    visited: set[int] = set()

    def visit(index: int) -> None:
        if index in visited:
            return
        visited.add(index)
        page = page_list[index]
        ordered.append(page)
        for child_index in children.get(str(page.get("id") or ""), []):
            visit(child_index)

    for index, root_parent_id in enumerate(parents):
        if root_parent_id is None:
            visit(index)
    for index in range(len(page_list)):
        visit(index)
    return ordered


def tree_containers(source: SourceConfig, data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_containers = data.get("containers") or []
    if raw_containers:
        result: list[dict[str, Any]] = []
        for item in raw_containers:
            if isinstance(item, dict):
                container_id = str(item.get("id") or item.get("key") or "")
                name = str(item.get("name") or container_id)
                key = str(item.get("key") or container_id)
                metadata = dict(item.get("metadata") or {})
            else:
                container_id = str(getattr(item, "id", ""))
                name = str(getattr(item, "name", "") or container_id)
                key = str(getattr(item, "key", None) or container_id)
                metadata = dict(getattr(item, "metadata", {}) or {})
            if container_id:
                result.append({
                    "id": container_id,
                    "key": key,
                    "name": name,
                    "description": metadata.get("description", ""),
                    "image_url": metadata.get("icon_url", ""),
                    "metadata": metadata,
                })
        return _deduplicate_containers(result)

    result_by_id: dict[str, dict[str, Any]] = {}
    for page in tree_pages(data):
        container_id = page_container_id(source, page)
        space = page.get("space") or {}
        result_by_id.setdefault(
            container_id,
            {
                "id": container_id,
                "key": str(space.get("key") or container_id),
                "name": str(space.get("name") or container_id),
                "description": "",
                "image_url": "",
                "metadata": {},
            },
        )
    return _deduplicate_containers(list(result_by_id.values()))


def _deduplicate_containers(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for container in containers:
        container_id = str(container.get("id") or "")
        if not container_id or container_id in seen:
            continue
        seen.add(container_id)
        result.append(container)
    return result


def explicit_visibility_kind(page: dict[str, Any]) -> str | None:
    metadata = page.get("metadata") or {}
    explicit = (
        page.get("visibility")
        or page.get("access")
        or page.get("permission")
        or metadata.get("visibility")
        or metadata.get("access")
        or metadata.get("permission")
    )
    if page.get("public") is True or metadata.get("public") is True or str(explicit).casefold() in {"public", "pública"}:
        return "public"
    if page.get("private") is True or metadata.get("private") is True or str(explicit).casefold() in {"private", "privada", "restricted"}:
        return "private"
    restrictions = (
        page.get("restrictions")
        or metadata.get("restrictions")
        or page.get("has_restrictions")
    )
    if restrictions is True:
        return "private"
    if restrictions is False:
        return "public"
    if isinstance(restrictions, dict):
        read = restrictions.get("read") or restrictions.get("view")
        if isinstance(read, dict):
            details = read.get("restrictions", read)
            if isinstance(details, dict):
                users = details.get("user")
                groups = details.get("group")
                u_res = users.get("results") if isinstance(users, dict) else (users if isinstance(users, list) else None)
                g_res = groups.get("results") if isinstance(groups, dict) else (groups if isinstance(groups, list) else None)
                if (isinstance(u_res, list) and len(u_res) > 0) or (isinstance(g_res, list) and len(g_res) > 0):
                    return "private"
                if u_res is not None or g_res is not None:
                    return "public"
        if bool(restrictions):
            return "private"

    if page.get("anonymous_access") is True:
        return "public"

    return None


def visibility_for_page(source: SourceConfig, page: dict[str, Any]) -> tuple[str, str]:
    kind = explicit_visibility_kind(page)
    if kind == "private":
        return "Privada", "private"
    if kind == "public":
        return "Pública", "public"
    if source.auth_mode == AuthMode.PUBLIC:
        return "Pública", "public"
    # Authenticated listings prove the current account can read the page, but
    # say nothing about anonymous reachability. Without explicit restriction
    # details, label the page as unknown instead of guessing private/public.
    return "Desconhecida", "unknown"


def visibility_for_container(source: SourceConfig, data: dict[str, Any], container: dict[str, Any]) -> tuple[str, str]:
    kind = explicit_visibility_kind(container)
    if kind == "private":
        return "Privada", "private"
    if kind == "public":
        return "Pública", "public"
    pages = tree_pages(data, str(container["id"]))
    page_kinds = [explicit_visibility_kind(page) for page in pages]
    known = [value for value in page_kinds if value is not None]
    if pages and len(known) == len(pages) and all(value == "private" for value in known):
        return "Privada", "private"
    return "Pública", "public"


def lazy_state(data: dict[str, Any], container_id: str) -> dict[str, Any]:
    lazy = data.setdefault("lazy_discovery", {})
    return lazy.setdefault(str(container_id), {"enabled": False, "loaded_parents": [], "fallback_reason": ""})
