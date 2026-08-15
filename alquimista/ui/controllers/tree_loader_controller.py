from __future__ import annotations

import concurrent.futures
import hashlib
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QProgressBar,
    QPushButton,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
)

from ...browser import BrowserCache, LazyDiscoveryService
from ...browser.adapters import ConnectorDiscoveryAdapter
from ...client import session_directory
from ...errors import AuthenticationError
from ...models import (
    AuthMode,
    ProjectConfig,
    SourceConfig,
    now_iso,
)
from ...runtime import CancellationToken
from ...session_store import load_session
from ..components import (
    AlchemistIconAtlas,
    SortableTreeItem,
    VisibilityBadgeDelegate,
    timestamp_sort_value,
)
from ..i18n import translate_text
from ..tree_models import (
    explicit_visibility_kind,
    ordered_pages,
    page_parent_id,
    parent_ids_in_list,
    visibility_for_container,
    visibility_for_page,
)
from ..tree_models import (
    lazy_state as tree_lazy_state,
)


class TreeLoaderController:
    """Coordinates space discovery, connector-driven tree loading, metadata caching, and lazy page expansion."""

    def __init__(
        self,
        connector_registry: Any,
        secrets: Any,
        trees: dict[str, Any] | Callable[[], dict[str, Any]],
        worker_starter: Callable[[Any, Any], None],
        lazy_discovery_page: Callable[..., Any | None] | None = None,
        status_bar: QStatusBar | None = None,
        tree_load_buttons: list[QPushButton] | None = None,
        tree_cancel_buttons: list[QPushButton] | None = None,
        tree_load_status_label: Any | None = None,
        tree_load_progress: QProgressBar | None = None,
    ) -> None:
        self._connector_registry = connector_registry
        self._secrets = secrets
        self._trees = trees
        self._worker_starter = worker_starter
        self._lazy_discovery_page = (
            lazy_discovery_page or self.lazy_discovery_page
        )
        self.status_bar = status_bar
        self.tree_load_buttons = tree_load_buttons or []
        self.tree_cancel_buttons = tree_cancel_buttons or []
        self.tree_load_status_label = tree_load_status_label
        self.tree_load_progress = tree_load_progress
        self.loading = False

    @property
    def connector_registry(self) -> Any:
        if callable(self._connector_registry):
            return self._connector_registry()
        return self._connector_registry

    @connector_registry.setter
    def connector_registry(self, value: Any) -> None:
        self._connector_registry = value

    @property
    def secrets(self) -> Any:
        if callable(self._secrets):
            return self._secrets()
        return self._secrets

    @secrets.setter
    def secrets(self, value: Any) -> None:
        self._secrets = value

    @property
    def trees(self) -> dict[str, Any]:
        if callable(self._trees):
            return self._trees()
        return self._trees

    @trees.setter
    def trees(self, value: dict[str, Any]) -> None:
        self._trees = value

    @property
    def worker_starter(self) -> Callable[[Any, Any], None]:
        return self._worker_starter

    @worker_starter.setter
    def worker_starter(self, value: Callable[[Any, Any], None]) -> None:
        self._worker_starter = value

    def set_loading(
        self,
        loading: bool,
        message: str | None = None,
        detail_active: bool = False,
    ) -> None:
        self.loading = loading
        idle_text = translate_text(
            "Carregar páginas" if detail_active else "Carregar espaços"
        )
        for btn in self.tree_load_buttons:
            btn.setEnabled(not loading)
            if loading:
                btn.setText(translate_text("⏳ Carregando…"))
                btn.setIcon(AlchemistIconAtlas.icon(7, 20))
            else:
                btn.setText(idle_text)
                btn.setIcon(AlchemistIconAtlas.icon(3, 20))
            btn.setIconSize(QSize(20, 20))

        for btn in self.tree_cancel_buttons:
            btn.setEnabled(loading)

        if self.tree_load_status_label is not None:
            self.tree_load_status_label.setText(
                translate_text(message)
                if message
                else (
                    translate_text("Carregando espaços e páginas…")
                    if loading
                    else translate_text("Pronto para carregar espaços.")
                )
            )

        if self.tree_load_progress is not None:
            self.tree_load_progress.setVisible(loading)
            if loading:
                self.tree_load_progress.setRange(0, 0)

        if loading and self.status_bar is not None:
            self.status_bar.showMessage(
                translate_text("Carregando espaços e páginas…")
            )

    def cancel_operation(self, token: CancellationToken | None) -> None:
        """Cancel an in-flight tree or space load immediately."""
        if not self.loading or token is None:
            return
        token.cancel()
        message = translate_text(
            "Cancelamento solicitado. Finalizando a requisição atual…"
        )
        if self.tree_load_status_label is not None:
            self.tree_load_status_label.setText(message)
        if self.status_bar is not None:
            self.status_bar.showMessage(message)

    def require_runnable_descriptor(self, source: SourceConfig) -> Any:
        descriptor = self.connector_registry.get(source.source_type)
        if not descriptor.runnable:
            raise ValueError(
                translate_text(
                    "A integração {name} ainda está em desenvolvimento."
                ).format(name=descriptor.display_name)
            )
        return descriptor

    def load_tree_via_connector(
        self,
        source: SourceConfig,
        project: ProjectConfig,
        on_done: Callable[[dict[str, Any]], None],
        descriptor: Any | None = None,
    ) -> None:
        descriptor = descriptor or self.require_runnable_descriptor(source)
        if not descriptor.runnable:
            raise ValueError(
                translate_text(
                    "A integração {name} ainda está em desenvolvimento."
                ).format(name=descriptor.display_name)
            )

        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> dict[str, Any]:
            progress(0, 1, translate_text("Descobrindo espaços"))
            connector = self.connector_registry.create(
                source,
                options=project.extraction,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            )
            try:
                containers = connector.list_containers()
            finally:
                connector.close()
            progress(
                1,
                1,
                translate_text("{count} espaços encontrados").format(
                    count=len(containers)
                ),
            )
            return {
                "root": {"id": "__all_containers__", "title": "Contêineres"},
                "containers": [
                    {
                        "id": str(container.id),
                        "key": str(container.key or container.id),
                        "name": str(container.name),
                        "description": str(container.description or ""),
                        "image_url": str(
                            (container.metadata or {}).get("icon_url", "")
                        ),
                        "metadata": dict(container.metadata or {}),
                    }
                    for container in containers
                ],
                "pages": [],
                "pages_by_container": {},
                "loaded_at": now_iso(),
            }

        self.worker_starter(work, on_done)

    @staticmethod
    def container_page_dict(
        container: dict[str, Any], item: Any
    ) -> dict[str, Any]:
        ancestors = []
        if hasattr(item, "metadata"):
            metadata = dict(getattr(item, "metadata", {}) or {})
            ancestors = list(metadata.get("ancestors", []) or [])
            updated_at = getattr(item, "updated_at", None)
            return {
                "id": str(getattr(item, "id", "")),
                "title": str(getattr(item, "title", "Sem título")),
                "type": str(getattr(item, "document_type", "page")),
                "ancestors": ancestors,
                "space": {
                    "key": container.get("key") or container["id"],
                    "name": container["name"],
                },
                "version": {
                    "number": metadata.get("confluence_version"),
                    "when": updated_at.isoformat() if updated_at else "",
                },
                "_container_id": str(container["id"]),
                "parent_id": getattr(item, "parent_id", None)
                or metadata.get("parent_id"),
                "has_children": bool(
                    getattr(item, "has_children", False)
                    or metadata.get("has_children", False)
                ),
                "original_url": str(getattr(item, "original_url", "") or ""),
                "etag": getattr(item, "etag", None) or metadata.get("etag"),
                "visibility": metadata.get("visibility")
                or getattr(getattr(item, "visibility", None), "value", None),
                "access": metadata.get("access"),
                "permission": metadata.get("permission"),
                "public": metadata.get("public"),
                "private": metadata.get("private"),
                "provider_ordered": bool(
                    metadata.get("provider_ordered", False)
                ),
            }
        page = dict(item)
        page["_container_id"] = str(container["id"])
        page.setdefault("parent_id", page.get("parentId"))
        page.setdefault("has_children", bool(page.get("hasChildren", False)))
        page.setdefault(
            "space",
            {
                "key": container.get("key") or container["id"],
                "name": container["name"],
            },
        )
        return page

    def load_all_containers(
        self,
        source: SourceConfig,
        project: ProjectConfig,
        containers: list[dict[str, Any]],
        on_done: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        self.require_runnable_descriptor(source)

        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> list[dict[str, Any]]:
            total_containers = len(containers)
            if total_containers == 0:
                return []

            if total_containers == 1:
                container = containers[0]
                connector = self.connector_registry.create(
                    source,
                    options=project.extraction,
                    secret=self.secrets.get(source.id, ""),
                    token=token,
                    log=log,
                )
                try:
                    token.check()
                    container_id = str(container["id"])
                    progress(
                        0,
                        1,
                        f"Abrindo {container['name']}",
                    )
                    documents = connector.list_documents(container_id)
                    pages = [
                        self.container_page_dict(container, item)
                        for item in documents
                    ]
                    progress(
                        1,
                        1,
                        f"{len(pages)} páginas em {container['name']}",
                    )
                    return [{"container_id": container_id, "pages": pages}]
                finally:
                    connector.close()

            results_by_id: dict[str, list[dict[str, Any]]] = {}
            max_workers = min(4, total_containers)
            completed_count = 0
            count_lock = threading.Lock()

            def _fetch_container(c: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
                nonlocal completed_count
                token.check()
                cid = str(c["id"])
                c_conn = self.connector_registry.create(
                    source,
                    options=project.extraction,
                    secret=self.secrets.get(source.id, ""),
                    token=token,
                    log=log,
                )
                try:
                    token.check()
                    docs = c_conn.list_documents(cid)
                    pgs = [
                        self.container_page_dict(c, item)
                        for item in docs
                    ]
                    with count_lock:
                        completed_count += 1
                        progress(
                            completed_count,
                            total_containers,
                            f"{len(pgs)} páginas em {c['name']}",
                        )
                    return (cid, pgs)
                finally:
                    c_conn.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(_fetch_container, c) for c in containers]
                for future in concurrent.futures.as_completed(futures):
                    cid, pgs = future.result()
                    results_by_id[cid] = pgs

            return [
                {"container_id": str(c["id"]), "pages": results_by_id.get(str(c["id"]), [])}
                for c in containers
            ]

        self.worker_starter(work, on_done)

    def load_container_for_source(
        self,
        source: SourceConfig,
        project: ProjectConfig,
        container: dict[str, Any],
        *,
        target: str,
        load_all: bool = False,
        cursor: str | None = None,
        on_done: Callable[[dict[str, Any]], None],
    ) -> None:
        descriptor = self.require_runnable_descriptor(source)
        container_id = str(container["id"])

        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> dict[str, Any]:
            progress(0, 1, f"Abrindo {container['name']}")
            lazy_enabled = False
            from_cache = False
            fallback_reason = ""
            connector = self.connector_registry.create(
                source,
                options=project.extraction,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            )
            try:
                page = (
                    None
                    if load_all
                    or not descriptor.capabilities.supports_lazy_discovery
                    else self._lazy_discovery_page(
                        source,
                        connector,
                        container_id,
                        parent_id=None,
                        token=token,
                        identity_secret=self.secrets.get(source.id, ""),
                        cursor=cursor,
                        supports_lazy_discovery=True,
                    )
                )
                if load_all or page is None:
                    fallback_reason = (
                        "Carregamento completo solicitado para este espaço."
                        if load_all
                        else "O conector não expõe descoberta lazy; carregando o inventário completo deste espaço."
                    )
                    documents = connector.list_documents(container_id)
                else:
                    lazy_enabled = True
                    documents = list(page.items)
                    from_cache = bool(page.from_cache)
                pages = [
                    self.container_page_dict(container, item)
                    for item in documents
                ]
                next_cursor = (
                    getattr(page, "next_cursor", None)
                    if page is not None
                    else None
                )
            finally:
                connector.close()
            progress(
                1, 1, f"{len(pages)} páginas encontradas em {container['name']}"
            )
            return {
                "container_id": container_id,
                "pages": pages,
                "target": target,
                "lazy_enabled": lazy_enabled,
                "roots_complete": bool(not lazy_enabled or not next_cursor),
                "inventory_complete": bool(load_all or not lazy_enabled),
                "fallback_reason": fallback_reason,
                "from_cache": from_cache,
                "next_cursor": next_cursor
                if "next_cursor" in locals()
                else None,
                "append": bool(cursor),
            }

        self.worker_starter(work, on_done)

    def load_document_children(
        self,
        source: SourceConfig,
        project: ProjectConfig,
        container: dict[str, Any],
        parent_id: str,
        *,
        target: str,
        cursor: str | None = None,
        on_done: Callable[[dict[str, Any]], None],
    ) -> None:
        descriptor = self.require_runnable_descriptor(source)
        if not descriptor.capabilities.supports_lazy_discovery:
            raise ValueError(
                translate_text(
                    "O conector não oferece descoberta lazy de filhos."
                )
            )
        container_id = str(container["id"])

        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> dict[str, Any]:
            progress(0, 1, f"Abrindo {parent_id}")
            connector = self.connector_registry.create(
                source,
                options=project.extraction,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            )
            try:
                page = self._lazy_discovery_page(
                    source,
                    connector,
                    container_id,
                    parent_id=parent_id,
                    token=token,
                    identity_secret=self.secrets.get(source.id, ""),
                    cursor=cursor,
                    supports_lazy_discovery=True,
                )
                if page is None and not hasattr(connector, "get_source"):
                    documents = self.lazy_documents(
                        connector,
                        container_id,
                        parent_id=parent_id,
                        token=token,
                    )
                    if documents is None:
                        raise RuntimeError("lazy child discovery is unavailable")
                    from_cache = False
                elif page is None:
                    raise RuntimeError(
                        "O conector não expõe list_document_children; nenhum inventário completo "
                        "foi executado para expandir esta pasta."
                    )
                else:
                    documents = list(page.items)
                    from_cache = bool(page.from_cache)
                pages = [
                    self.container_page_dict(container, item)
                    for item in documents
                ]
            finally:
                connector.close()
            progress(1, 1, f"{len(pages)} filhos encontrados")
            return {
                "container_id": container_id,
                "parent_id": parent_id,
                "pages": pages,
                "target": target,
                "from_cache": from_cache,
                "next_cursor": getattr(page, "next_cursor", None)
                if page is not None
                else None,
                "append": bool(cursor),
            }

        self.worker_starter(work, on_done)

    @staticmethod
    def page_visibility(
        source: SourceConfig, page: dict[str, Any]
    ) -> tuple[str, str]:
        return visibility_for_page(source, page)

    @staticmethod
    def explicit_visibility_kind(page: dict[str, Any]) -> str | None:
        return explicit_visibility_kind(page)

    @staticmethod
    def container_visibility(
        source: SourceConfig,
        data: dict[str, Any],
        container: dict[str, Any],
    ) -> tuple[str, str]:
        return visibility_for_container(source, data, container)

    @staticmethod
    def lazy_method(connector: Any, operation: str) -> Any:
        service = getattr(connector, "lazy_service", None) or getattr(
            connector, "discovery_service", None
        )
        owner = service or connector
        if operation == "root":
            return getattr(owner, "list_root_documents", None)
        return getattr(owner, "list_document_children", None) or getattr(
            owner, "list_children", None
        )

    @staticmethod
    def browser_cache_path() -> Path:
        import sys
        mw = sys.modules.get("alquimista.ui.main_window")
        if mw is not None and hasattr(mw, "session_directory"):
            return mw.session_directory().parent / "browser_metadata.sqlite3"
        return session_directory().parent / "browser_metadata.sqlite3"

    @classmethod
    def browser_cache_scope(
        cls,
        source: SourceConfig,
        *,
        connector: Any | None = None,
        identity_secret: str = "",
    ) -> str | None:
        mode = source.auth_mode
        if mode == AuthMode.PUBLIC:
            return "public-v2"
        material: object | None = None
        identity = getattr(connector, "get_auth_identity", None)
        if callable(identity):
            try:
                material = identity()
            except (AttributeError, TypeError, ValueError, RuntimeError):
                material = None
        if material is None:
            material = (
                identity_secret or getattr(connector, "secret", "") or None
            )
        if material is None and mode == AuthMode.BROWSER:
            try:
                state = load_session(source.id)
                cookies = (
                    state.get("cookies", []) if isinstance(state, dict) else []
                )
                material = [
                    {
                        "name": item.get("name", ""),
                        "value": item.get("value", ""),
                        "domain": item.get("domain", ""),
                        "path": item.get("path", "/"),
                    }
                    for item in cookies
                    if isinstance(item, dict)
                ]
            except (AuthenticationError, OSError, TypeError, ValueError):
                material = None
        if material is None or material == "":
            return None
        payload = {
            "version": 2,
            "source": source.id,
            "origin": source.base_url.rstrip("/").casefold(),
            "mode": mode.value,
            "material": material,
        }
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return f"auth-v2:{digest}"

    @classmethod
    def lazy_discovery_page(
        cls,
        source: SourceConfig,
        connector: Any,
        container_id: str,
        *,
        parent_id: str | None,
        token: CancellationToken,
        cursor: str | None = None,
        identity_secret: str = "",
        supports_lazy_discovery: bool = True,
    ) -> Any | None:
        if not supports_lazy_discovery:
            return None
        adapter = ConnectorDiscoveryAdapter(connector)
        capability = (
            "list_document_children" if parent_id else "list_root_documents"
        )
        if (
            capability not in adapter.capabilities
            or not hasattr(connector, "get_source")
        ):
            return None
        cache_scope = cls.browser_cache_scope(
            source,
            connector=connector,
            identity_secret=identity_secret,
        )
        cache = (
            BrowserCache(cls.browser_cache_path()) if cache_scope else None
        )
        service = LazyDiscoveryService(
            source.id,
            adapter,
            cache=cache,
            cache_scope=cache_scope or "network-only",
        )
        if parent_id:
            return service.list_document_children(
                container_id,
                parent_id,
                cursor=cursor,
                limit=800,
                token=token,
            )
        return service.list_root_documents(
            container_id, cursor=cursor, limit=800, token=token
        )

    @classmethod
    def lazy_documents(
        cls,
        connector: Any,
        container_id: str,
        *,
        parent_id: str | None,
        token: CancellationToken,
    ) -> list[Any] | None:
        method = cls.lazy_method(connector, "children" if parent_id else "root")
        if not callable(method):
            return None
        if parent_id:
            result = method(
                container_id,
                parent_id,
                cursor=None,
                limit=800,
                token=token,
            )
        else:
            result = method(container_id, cursor=None, limit=800, token=token)
        items = getattr(result, "items", result)
        return list(items or [])

    @staticmethod
    def lazy_state(data: dict[str, Any], container_id: str) -> dict[str, Any]:
        return tree_lazy_state(data, container_id)

    def populate_page_tree_lazy(
        self,
        tree: QTreeWidget,
        source: SourceConfig,
        data: dict[str, Any],
        tree_pages_fn: Callable[..., list[dict[str, Any]]],
        *,
        container_id: str,
    ) -> list[dict[str, Any]]:
        tree.setSortingEnabled(False)
        tree.clear()
        pages = tree_pages_fn(data, container_id)
        state = self.lazy_state(data, container_id)
        loaded_parents = {
            str(value) for value in state.get("loaded_parents", [])
        }
        page_ids = {
            str(page.get("id", "")) for page in pages if page.get("id")
        }
        parent_ids = parent_ids_in_list(pages)
        document_nodes: dict[str, QTreeWidgetItem] = {}

        for page in ordered_pages(pages):
            page_id = str(page.get("id", ""))
            parent_id = page_parent_id(page, page_ids)
            parent = document_nodes.get(parent_id) if parent_id else None
            visibility, visibility_kind = self.page_visibility(source, page)
            version = page.get("version", {}) or {}
            title = str(page.get("title", "Sem título"))
            raw_type = str(page.get("type", "page"))
            type_label = {
                "page": "Página",
                "folder": "Pasta",
                "space": "Espaço",
            }.get(raw_type.casefold(), raw_type)
            item = SortableTreeItem(
                [
                    title,
                    type_label,
                    page_id,
                    "Página raiz" if not parent_id else parent_id,
                    "",
                    str(version.get("number", "")),
                    str(version.get("when", "")),
                ]
            )
            item.setData(0, VisibilityBadgeDelegate.TITLE_ROLE, title)
            icon = (
                "\U0001f4c1"
                if (page_id in parent_ids or bool(page.get("has_children")))
                else "\U0001f4c4"
            )
            item.setData(0, VisibilityBadgeDelegate.ICON_ROLE, icon)
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_ROLE, visibility)
            item.setData(
                0,
                VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE,
                visibility_kind,
            )
            item.setData(0, VisibilityBadgeDelegate.SOURCE_ROLE, source.id)
            item.setData(0, VisibilityBadgeDelegate.CONTAINER_ROLE, container_id)
            item.setData(0, VisibilityBadgeDelegate.DOCUMENT_ROLE, page_id)
            item.setData(0, SortableTreeItem.SORT_ROLE, title.casefold())
            (
                parent.addChild(item)
                if parent
                else tree.addTopLevelItem(item)
            )
            document_nodes[page_id] = item
            if (
                not parent_id or bool(page.get("has_children"))
            ) and page_id not in loaded_parents:
                item.setChildIndicatorPolicy(
                    QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
                )

        tree.setSortingEnabled(False)
        tree.setProperty("_alquimista_sort_column", -1)
        tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = tree.header()
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
        return pages

    def populate_page_tree(
        self,
        tree: QTreeWidget,
        source: SourceConfig,
        data: dict[str, Any],
        tree_pages_fn: Callable[..., list[dict[str, Any]]],
        *,
        container_id: str | None = None,
        render_limit: int = 800,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        sorting = tree.isSortingEnabled()
        tree.setSortingEnabled(False)
        tree.clear()
        root_id = str(data.get("root", {}).get("id", "__all_containers__"))
        all_pages = ordered_pages(tree_pages_fn(data, container_id))
        pages = all_pages[:render_limit]
        page_parent_ids = parent_ids_in_list(pages)
        if container_id and self.lazy_state(data, container_id).get("enabled"):
            tree.setSortingEnabled(sorting)
            lazy_pages = self.populate_page_tree_lazy(
                tree,
                source,
                data,
                tree_pages_fn,
                container_id=str(container_id),
            )
            return lazy_pages, all_pages

        rich_rows = False
        page_ids = {
            str(page.get("id") or "") for page in pages if page.get("id")
        }
        document_nodes: dict[str, QTreeWidgetItem] = {}
        parent_by_page: dict[str, str | None] = {}

        def ancestor_chain(page: dict[str, Any]) -> list[dict[str, Any]]:
            ancestors = list(page.get("ancestors", []) or [])
            ids = [
                str(item.get("id"))
                for item in ancestors
                if isinstance(item, dict)
            ]
            if root_id in ids:
                ancestors = ancestors[ids.index(root_id) + 1 :]
            elif str(page.get("id")) == root_id:
                ancestors = []
            return [item for item in ancestors if isinstance(item, dict)]

        def path_parts(page: dict[str, Any]) -> list[str]:
            return [str(item.get("title", "")) for item in ancestor_chain(page)]

        for page in pages:
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            parts = path_parts(page)
            parent_by_page[page_id] = page_parent_id(page, page_ids)
            version = page.get("version", {}) or {}
            visibility, visibility_kind = self.page_visibility(source, page)
            title = str(page.get("title", "Sem título"))
            raw_type = str(page.get("type", "page"))
            type_label = {
                "page": "Página",
                "folder": "Pasta",
                "space": "Espaço",
            }.get(raw_type.casefold(), raw_type)
            item = SortableTreeItem(
                [
                    title if rich_rows else f"📄 {title}",
                    type_label,
                    str(page.get("id", "")),
                    parts[0] if parts else "Página raiz",
                    " > ".join(parts),
                    str(version.get("number", "")),
                    str(version.get("when", "")),
                ]
            )
            item.setText(0, title)
            sort_values = [
                str(page.get("title", "")).casefold(),
                str(page.get("type", "page")).casefold(),
                int(page["id"])
                if str(page.get("id", "")).isdigit()
                else str(page.get("id", "")),
                (parts[0] if parts else "Página raiz").casefold(),
                " > ".join(parts).casefold(),
                int(version.get("number", 0) or 0),
                timestamp_sort_value(str(version.get("when", ""))),
            ]
            for column, value in enumerate(sort_values):
                item.setData(column, SortableTreeItem.SORT_ROLE, value)
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_ROLE, visibility)
            item.setData(
                0,
                VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE,
                visibility_kind,
            )
            item.setData(0, VisibilityBadgeDelegate.TITLE_ROLE, title)
            legacy_icon = (
                "\U0001f4c1"
                if str(page.get("id", "")) in page_parent_ids
                else "\U0001f4c4"
            )
            item.setData(0, VisibilityBadgeDelegate.ICON_ROLE, legacy_icon)
            item.setData(0, VisibilityBadgeDelegate.SOURCE_ROLE, source.id)
            item.setData(
                0,
                VisibilityBadgeDelegate.CONTAINER_ROLE,
                str(container_id or ""),
            )
            item.setData(0, VisibilityBadgeDelegate.DOCUMENT_ROLE, page_id)
            item.setData(0, VisibilityBadgeDelegate.RICH_ROW_ROLE, rich_rows)
            document_nodes[page_id] = item

        hierarchy_nodes: dict[str, QTreeWidgetItem] = dict(document_nodes)
        for page in pages:
            page_id = str(page.get("id") or "")
            document_item: QTreeWidgetItem | None = document_nodes.get(page_id)
            if document_item is None:
                continue
            anchor: QTreeWidgetItem | None = None
            accumulated_titles: list[str] = []
            for ancestor in ancestor_chain(page):
                ancestor_id = str(ancestor.get("id") or "")
                if not ancestor_id or ancestor_id == page_id:
                    continue
                ancestor_title = str(ancestor.get("title") or "Pasta")
                accumulated_titles.append(ancestor_title)
                parent_node: QTreeWidgetItem | None = hierarchy_nodes.get(
                    ancestor_id
                )
                if parent_node is None:
                    parent_node = SortableTreeItem(
                        [
                            f"📁 {ancestor_title}",
                            "Pasta",
                            ancestor_id,
                            ancestor_title,
                            " > ".join(accumulated_titles),
                            "",
                            "",
                        ]
                    )
                    parent_node.setText(0, ancestor_title)
                    parent_node.setData(
                        0, VisibilityBadgeDelegate.TITLE_ROLE, ancestor_title
                    )
                    parent_node.setData(
                        0, VisibilityBadgeDelegate.ICON_ROLE, "📁"
                    )
                    parent_node.setData(
                        0,
                        VisibilityBadgeDelegate.VISIBILITY_ROLE,
                        "Raiz" if anchor is None else "Pasta",
                    )
                    parent_node.setData(
                        0,
                        VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE,
                        "root" if anchor is None else "folder",
                    )
                    if anchor is None:
                        tree.addTopLevelItem(parent_node)
                    else:
                        anchor.addChild(parent_node)
                    hierarchy_nodes[ancestor_id] = parent_node
                anchor = parent_node
            parent = anchor or hierarchy_nodes.get(
                parent_by_page.get(page_id) or ""
            )
            if parent is None:
                tree.addTopLevelItem(document_item)
            else:
                parent.addChild(document_item)
        tree.setSortingEnabled(False)
        tree.setProperty("_alquimista_sort_column", -1)
        tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = tree.header()
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
        tree.expandToDepth(1)
        return pages, all_pages


__all__ = ["TreeLoaderController"]
