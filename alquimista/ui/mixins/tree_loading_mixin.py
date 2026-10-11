from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QTreeWidgetItem

from ...models import (
    SourceConfig,
    now_iso,
)
from ...runtime import CancellationToken
from ..components import (
    AlchemistIconAtlas,
    VisibilityBadgeDelegate,
)
from ..controllers import TreeLoaderController
from ..i18n import translate_text
from . import WindowBase


class TreeLoadingMixin(WindowBase):
    """Loading containers, page trees and lazy children into the selection views."""

    # Attributes and methods provided by MainWindow or sibling mixins.
    _active_page_container: str | None
    _active_selection_container: str | None
    _page_render_key: Any
    _page_render_limits: Any
    _populate_selection_tree: Any
    _refresh_page_summary: Any
    _refresh_pages_home: Any
    _refresh_selection_home: Any
    _selection_source: Any
    _tree_containers: Any
    _tree_pages: Any
    page_load_more_button: Any
    page_render_status: Any
    page_tree: Any
    pages_stack: Any
    project: Any
    selection_stack: Any
    source_by_combo: Any
    token: Any
    tree_empty: Any
    tree_loader_controller: Any
    trees: Any
    worker: Any

    def _tree_source_changed(self) -> None:
        source = self.source_by_combo(
            getattr(
                self,
                "tree_source",
                getattr(self, "selection_source", None),
            )
        )
        if source and source.id in self.trees:
            self._active_page_container = None
            if hasattr(self, "pages_stack"):
                self.pages_stack.setCurrentIndex(0)
            self._update_load_context()
            self._refresh_pages_home()
            self._refresh_selection_home()
        else:
            self._active_page_container = None
            self._update_load_context()
            self.page_tree.clear()
            self.tree_empty.setVisible(True)
            self._refresh_page_summary(source)
            self._refresh_pages_home()

    def _update_load_context(self) -> None:
        page_detail = bool(
            getattr(self, "pages_stack", None)
            and self.pages_stack.currentIndex() == 1
            and self._active_page_container
        )
        selection_detail = bool(
            getattr(self, "selection_stack", None)
            and self.selection_stack.currentIndex() == 1
            and self._active_selection_container
        )
        page_text = translate_text(
            "Carregar páginas" if page_detail else "Carregar espaços"
        )
        selection_text = translate_text(
            "Carregar páginas" if selection_detail else "Carregar espaços"
        )
        if hasattr(self, "tree_load_button"):
            self.tree_load_button.setText(page_text)
            self.tree_load_button.setIcon(AlchemistIconAtlas.icon(3, 20))
            self.tree_load_button.setIconSize(QSize(20, 20))
        if hasattr(self, "selection_load_button"):
            self.selection_load_button.setText(selection_text)
            self.selection_load_button.setIcon(AlchemistIconAtlas.icon(3, 20))
            self.selection_load_button.setIconSize(QSize(20, 20))

    def _set_tree_loading(
        self, loading: bool, message: str | None = None
    ) -> None:
        self.tree_loader_controller.set_loading(
            loading,
            message,
            detail_active=bool(
                self._active_page_container
                or self._active_selection_container
            ),
        )

    def _cancel_tree_operation(self) -> None:
        self.tree_loader_controller.cancel_operation(self.token)

    def load_tree(self) -> None:
        if (
            getattr(self, "pages_stack", None)
            and self.pages_stack.currentIndex() == 1
            and self._active_page_container
        ):
            source = self.source_by_combo(
                getattr(
                    self,
                    "tree_source",
                    getattr(self, "selection_source", None),
                )
            )
            if source:
                self._load_container_for_source(
                    source,
                    self._active_page_container,
                    target="pages",
                    load_all=True,
                )
            return
        if (
            getattr(self, "selection_stack", None)
            and self.selection_stack.currentIndex() == 1
            and self._active_selection_container
        ):
            source = self._selection_source()
            if source:
                self._load_container_for_source(
                    source,
                    self._active_selection_container,
                    target="selection",
                    load_all=True,
                )
            return
        source = self.source_by_combo(
            getattr(
                self,
                "tree_source",
                getattr(self, "selection_source", None),
            )
        )
        if not source:
            return
        if self.worker is not None:
            if hasattr(self, "tree_load_status"):
                self.tree_load_status.setText(
                    translate_text("Já existe uma operação em andamento…")
                )
            return
        try:
            descriptor = self._require_runnable_descriptor(source)
        except ValueError as exc:
            message = str(exc)
            self._set_tree_loading(False, message)
            self.statusBar().showMessage(message, 5000)
            return
        self._set_tree_loading(True)
        self._load_tree_via_connector(source, descriptor=descriptor)

    def _require_runnable_descriptor(self, source: SourceConfig) -> Any:
        return self.tree_loader_controller.require_runnable_descriptor(source)

    def _load_tree_via_connector(
        self, source: SourceConfig, *, descriptor: Any | None = None
    ) -> None:
        def on_done(data: dict[str, Any]) -> None:
            self.trees[source.id] = data
            self._active_page_container = None
            if hasattr(self, "pages_stack"):
                self.pages_stack.setCurrentIndex(0)
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False,
                translate_text(
                    "{count} espaços encontrados. Escolha um para carregar."
                ).format(count=len(data["containers"])),
            )
            self.statusBar().showMessage(
                translate_text(
                    "{count} espaços encontrados. Escolha um para carregar."
                ).format(count=len(data["containers"])),
                5000,
            )

        try:
            self.tree_loader_controller.load_tree_via_connector(
                source, self.project, on_done, descriptor=descriptor
            )
        except ValueError as exc:
            message = str(exc)
            self._set_tree_loading(False, message)
            self.statusBar().showMessage(message, 5000)

    @staticmethod
    def _container_page_dict(
        container: dict[str, Any], item: Any
    ) -> dict[str, Any]:
        return TreeLoaderController.container_page_dict(container, item)

    def _load_all_containers(self) -> None:
        sender = self.sender()
        source = (
            self._selection_source()
            if sender is getattr(self, "selection_load_button", None)
            else self.source_by_combo(
                getattr(
                    self,
                    "tree_source",
                    getattr(self, "selection_source", None),
                )
            )
        )
        if not source:
            return
        data = self.trees.get(source.id)
        if not data or self.worker is not None:
            return
        loaded = data.get("pages_by_container") or {}
        containers = [
            container
            for container in self._tree_containers(source, data)
            if str(container["id"]) not in loaded
        ]
        if not containers:
            self._set_tree_loading(
                False, "Todos os espaços já estão carregados."
            )
            return

        try:
            self._require_runnable_descriptor(source)
        except ValueError as exc:
            message = str(exc)
            self._set_tree_loading(False, message)
            self.statusBar().showMessage(message, 5000)
            return

        self._set_tree_loading(
            True, f"Carregando 0 de {len(containers)} espaços…"
        )

        def on_done(results: list[dict[str, Any]]) -> None:
            current = self.trees.setdefault(source.id, data)
            pages_by_container = current.setdefault("pages_by_container", {})
            for result in results:
                pages_by_container[str(result["container_id"])] = result[
                    "pages"
                ]
            current["pages"] = self._tree_pages(current)
            current["loaded_at"] = now_iso()
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False,
                f"{len(results)} espaços carregados. Escolha um para visualizar.",
            )

        self.tree_loader_controller.load_all_containers(
            source, self.project, containers, on_done
        )

    def _load_container_for_source(
        self,
        source: SourceConfig,
        container_id: str,
        *,
        target: str,
        load_all: bool = False,
        cursor: str | None = None,
        on_loaded: Callable[[], None] | None = None,
    ) -> None:
        data = self.trees.get(source.id)
        if data is None or self.worker is not None:
            return
        try:
            self._require_runnable_descriptor(source)
        except ValueError as exc:
            message = str(exc)
            self._set_tree_loading(False, message)
            self.statusBar().showMessage(message, 5000)
            return
        container = next(
            (
                item
                for item in self._tree_containers(source, data)
                if item["id"] == container_id
            ),
            {"id": container_id, "key": container_id, "name": container_id},
        )
        self._set_tree_loading(
            True, f"Carregando páginas de {container['name']}…"
        )

        def on_done(result: dict[str, Any]) -> None:
            current = self.trees.setdefault(source.id, data)
            pages_by_container = current.setdefault("pages_by_container", {})
            if result.get("append"):
                existing = pages_by_container.setdefault(container_id, [])
                known = {str(item.get("id", "")) for item in existing}
                existing.extend(
                    item
                    for item in result["pages"]
                    if str(item.get("id", "")) not in known
                )
            else:
                pages_by_container[container_id] = result["pages"]
            lazy_state = current.setdefault("lazy_discovery", {}).setdefault(
                container_id, {}
            )
            lazy_state.update(
                {
                    "enabled": bool(result.get("lazy_enabled")),
                    "roots_complete": bool(result.get("roots_complete")),
                    "inventory_complete": bool(
                        result.get("inventory_complete")
                    ),
                    "full_loaded": bool(result.get("inventory_complete")),
                    "loaded_parents": lazy_state.get("loaded_parents", []),
                    "fallback_reason": str(result.get("fallback_reason", "")),
                    "next_cursor": result.get("next_cursor"),
                    "truncated": bool(result.get("next_cursor")),
                }
            )
            current["pages"] = self._tree_pages(current)
            current["loaded_at"] = now_iso()
            if self._active_page_container == container_id:
                self._populate_page_tree(
                    source, current, container_id=container_id
                )
            if self._active_selection_container == container_id:
                self._populate_selection_tree(
                    source, current, container_id=container_id
                )
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False,
                (
                    translate_text(
                        "{count} páginas-raiz carregadas em {name}."
                    ).format(
                        count=len(result["pages"]), name=container["name"]
                    )
                    if result.get("lazy_enabled")
                    and not result.get("inventory_complete")
                    else translate_text(
                        "{count} páginas carregadas em {name}."
                    ).format(
                        count=len(result["pages"]), name=container["name"]
                    )
                ),
            )
            self.statusBar().showMessage(
                str(
                    result.get("fallback_reason")
                    or translate_text(
                        "{count} páginas carregadas em {name}."
                    ).format(
                        count=len(result["pages"]), name=container["name"]
                    )
                ),
                7000,
            )
            if result.get("from_cache"):
                self.statusBar().showMessage(
                    translate_text("Resultado reutilizado do cache local."),
                    7000,
                )
            if on_loaded is not None:
                on_loaded()

        self.tree_loader_controller.load_container_for_source(
            source,
            self.project,
            container,
            target=target,
            load_all=load_all,
            cursor=cursor,
            on_done=on_done,
        )

    def _page_visibility(
        self, source: SourceConfig, page: dict[str, Any]
    ) -> tuple[str, str]:
        return TreeLoaderController.page_visibility(source, page)

    @staticmethod
    def _explicit_visibility_kind(page: dict[str, Any]) -> str | None:
        return TreeLoaderController.explicit_visibility_kind(page)

    def _container_visibility(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        container: dict[str, Any],
    ) -> tuple[str, str]:
        return TreeLoaderController.container_visibility(
            source, data, container
        )

    @staticmethod
    def _lazy_method(connector: Any, operation: str) -> Any:
        return TreeLoaderController.lazy_method(connector, operation)

    @staticmethod
    def _browser_cache_path() -> Path:
        return TreeLoaderController.browser_cache_path()

    @classmethod
    def _browser_cache_scope(
        cls,
        source: SourceConfig,
        *,
        connector: Any | None = None,
        identity_secret: str = "",
    ) -> str | None:
        return TreeLoaderController.browser_cache_scope(
            source, connector=connector, identity_secret=identity_secret
        )

    @classmethod
    def _lazy_discovery_page(
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
        return TreeLoaderController.lazy_discovery_page(
            source,
            connector,
            container_id,
            parent_id=parent_id,
            token=token,
            cursor=cursor,
            identity_secret=identity_secret,
            supports_lazy_discovery=supports_lazy_discovery,
        )

    @classmethod
    def _lazy_documents(
        cls,
        connector: Any,
        container_id: str,
        *,
        parent_id: str | None,
        token: CancellationToken,
    ) -> list[Any] | None:
        return TreeLoaderController.lazy_documents(
            connector, container_id, parent_id=parent_id, token=token
        )

    @staticmethod
    def _lazy_state(data: dict[str, Any], container_id: str) -> dict[str, Any]:
        return TreeLoaderController.lazy_state(data, container_id)

    def _page_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        self._load_expanded_document(item, target="pages")

    def _load_expanded_document(
        self, item: QTreeWidgetItem, *, target: str
    ) -> None:
        source_id = str(item.data(0, VisibilityBadgeDelegate.SOURCE_ROLE) or "")
        container_id = str(
            item.data(0, VisibilityBadgeDelegate.CONTAINER_ROLE) or ""
        )
        document_id = str(
            item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE) or ""
        )
        if not source_id or not container_id or not document_id:
            return
        source = next(
            (
                candidate
                for candidate in self.project.sources
                if candidate.id == source_id
            ),
            None,
        )
        data = self.trees.get(source_id)
        if source is None or data is None:
            return
        state = self._lazy_state(data, container_id)
        child_cursors = state.get("child_cursors", {}) or {}
        if not state.get("enabled") or (
            document_id in state.get("loaded_parents", [])
            and not child_cursors.get(document_id)
        ):
            return
        if self.worker is not None:
            self.statusBar().showMessage(
                translate_text("Aguarde o carregamento atual terminar."), 3000
            )
            return
        self._load_document_children(
            source,
            data,
            container_id,
            document_id,
            target=target,
            cursor=str(child_cursors.get(document_id))
            if child_cursors.get(document_id)
            else None,
        )

    def _load_document_children(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        container_id: str,
        parent_id: str,
        *,
        target: str,
        cursor: str | None = None,
    ) -> None:
        try:
            self._require_runnable_descriptor(source)
        except ValueError as exc:
            message = str(exc)
            self._set_tree_loading(False, message)
            self.statusBar().showMessage(message, 5000)
            return
        container = next(
            (
                item
                for item in self._tree_containers(source, data)
                if item["id"] == container_id
            ),
            {"id": container_id, "key": container_id, "name": container_id},
        )
        self._set_tree_loading(True, f"Carregando filhos de {parent_id}…")

        def on_done(result: dict[str, Any]) -> None:
            current = self.trees.setdefault(source.id, data)
            pages_by_container = current.setdefault("pages_by_container", {})
            pages = pages_by_container.setdefault(container_id, [])
            known_ids = {str(page.get("id", "")) for page in pages}
            pages.extend(
                page
                for page in result["pages"]
                if str(page.get("id", "")) not in known_ids
            )
            state = self._lazy_state(current, container_id)
            loaded_parents = list(state.get("loaded_parents", []))
            if parent_id not in loaded_parents:
                loaded_parents.append(parent_id)
            state["loaded_parents"] = loaded_parents
            child_cursors = state.setdefault("child_cursors", {})
            if result.get("next_cursor"):
                child_cursors[parent_id] = result["next_cursor"]
            else:
                child_cursors.pop(parent_id, None)
            current["pages"] = self._tree_pages(current)
            current["loaded_at"] = now_iso()
            if self._active_page_container == container_id:
                self._populate_page_tree(
                    source, current, container_id=container_id
                )
            if self._active_selection_container == container_id:
                self._populate_selection_tree(
                    source, current, container_id=container_id
                )
            self._refresh_pages_home()
            self._refresh_selection_home()
            suffix = " (cache local)" if result.get("from_cache") else ""
            self._set_tree_loading(
                False,
                translate_text("{count} filhos carregados{suffix}.").format(
                    count=len(result["pages"]), suffix=suffix
                ),
            )
            if result.get("from_cache"):
                self.statusBar().showMessage(
                    translate_text("Filhos reutilizados do cache local."), 7000
                )

        try:
            self.tree_loader_controller.load_document_children(
                source,
                self.project,
                container,
                parent_id,
                target=target,
                cursor=cursor,
                on_done=on_done,
            )
        except Exception as exc:
            message = str(exc)
            self._set_tree_loading(False, message)
            self.statusBar().showMessage(message, 5000)

    def _populate_page_tree_lazy(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        *,
        container_id: str,
    ) -> None:
        pages = self.tree_loader_controller.populate_page_tree_lazy(
            self.page_tree,
            source,
            data,
            self._tree_pages,
            container_id=container_id,
        )
        self.tree_empty.setVisible(False)
        self._refresh_page_summary(source, {**data, "pages": pages})
        state = self._lazy_state(data, container_id)
        self.page_render_status.setText(
            translate_text(
                "Mostrando {count:,} páginas carregadas. "
                "Expanda uma pasta ou página-pai para buscar os filhos."
            ).format(count=len(pages))
        )
        self.page_load_more_button.setVisible(bool(state.get("next_cursor")))

    def _populate_page_tree(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        *,
        container_id: str | None = None,
    ) -> None:
        key = self._page_render_key(source, str(container_id or ""))
        limit = self._page_render_limits.get(key, 800)
        pages, all_pages = self.tree_loader_controller.populate_page_tree(
            self.page_tree,
            source,
            data,
            self._tree_pages,
            container_id=container_id,
            render_limit=limit,
        )
        if container_id and self._lazy_state(data, container_id).get("enabled"):
            self.tree_empty.setVisible(False)
            self._refresh_page_summary(source, {**data, "pages": pages})
            state = self._lazy_state(data, container_id)
            self.page_render_status.setText(
                translate_text(
                    "Mostrando {count:,} páginas carregadas. "
                    "Expanda uma pasta ou página-pai para buscar os filhos."
                ).format(count=len(pages))
            )
            self.page_load_more_button.setVisible(bool(state.get("next_cursor")))
            return
        self.page_tree.expandToDepth(1)
        self.tree_empty.setVisible(False)
        self._refresh_page_summary(source, {**data, "pages": pages})
        self.page_render_status.setText(
            translate_text(
                "Mostrando {visible:,} de {total:,} páginas. "
                "O carregamento legado mantém apenas os metadados já descobertos."
            ).format(visible=len(pages), total=len(all_pages))
        )
        self.page_load_more_button.setVisible(len(pages) < len(all_pages))
