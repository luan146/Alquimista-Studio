"""Selection page behavior for the main window."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QListWidgetItem, QMenu, QTreeWidgetItem

from ...models import SourceConfig
from ...selection import SelectionStore
from ..components import SortableTreeItem, VisibilityBadgeDelegate, timestamp_sort_value
from ..i18n import translate_text
from ..space_cards import SpaceCardDelegate
from ..tree_models import display_timestamp, ordered_pages, page_parent_id, parent_ids_in_list, relative_timestamp
from . import WindowBase


class SelectionMixin(WindowBase):
    """Selection navigation, filtering, and persistence behavior."""

    # Attributes provided by MainWindow.__init__/build_selection_page. See
    # TreeMixin for the same pattern: annotations only, no initializers.
    project: Any
    trees: Any
    current_source: Any
    source_by_combo: Any
    mark_dirty: Any
    selection_stack: Any
    selection_source: Any
    selection_search: Any
    selection_filter: Any
    selection_spaces: Any
    selection_total: Any
    _preview_real_page: Any
    selection_count: Any
    selection_home_empty: Any
    selection_render_status: Any
    selection_load_more_button: Any
    selection_space_search: Any
    selection_space_title: Any
    selection_tree: Any
    _active_selection_container: str | None
    _selection_render_limits: dict[tuple[str, str], int]
    _page_render_key: Any
    _tree_pages: Any
    _page_container_id: Any
    _lazy_state: Any
    _container_loaded: Any
    _container_requires_full_load: Any
    _container_visibility: Any
    _page_visibility: Any
    _selection_containers: Any
    _load_container_for_source: Any
    _load_expanded_document: Any
    _update_load_context: Any
    _update_extraction_summary: Any
    statusBar: Any
    worker: Any

    def _selection_source_changed(self) -> None:
        if not hasattr(self, "selection_stack"):
            return
        self._active_selection_container = None
        self.selection_stack.setCurrentIndex(0)
        self._refresh_selection_home()



    def _selection_source(self) -> SourceConfig | None:
        return self.source_by_combo(self.selection_source)

    def _refresh_selection_home(self) -> None:
        """Spaces of the selected source as painted cards with a whole-space pill."""
        if not hasattr(self, "selection_home_layout"):
            return
        source = self._selection_source()
        containers = self._selection_containers(source) if source else []
        view = self.selection_spaces
        view.clear()
        if not containers or source is None:
            self.selection_home_empty.setVisible(True)
            self.selection_space_search.setVisible(False)
            view.setVisible(False)
            self.selection_total.setVisible(False)
            return
        self.selection_home_empty.setVisible(False)
        self.selection_space_search.setVisible(True)
        view.setVisible(True)
        data = self.trees.get(source.id, {})
        total_selected = 0
        spaces_with_selection = 0
        for container in containers:
            container_id = str(container["id"])
            name = str(container["name"])
            pages = int(container.get("pages") or 0)
            selected = int(container.get("selected") or 0)
            total_selected += selected
            spaces_with_selection += bool(selected)
            visibility, _kind = self._container_visibility(source, data, container)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, container_id)
            item.setData(SpaceCardDelegate.NAME_ROLE, name)
            item.setData(SpaceCardDelegate.PAGES_ROLE, pages)
            item.setData(SpaceCardDelegate.SELECTED_ROLE, selected)
            item.setData(SpaceCardDelegate.LOADED_ROLE, bool(container.get("loaded")) or bool(pages))
            item.setData(Qt.ItemDataRole.AccessibleTextRole, f"{name}: {selected}/{pages}")
            item.setToolTip(f"{name}\n{visibility}" if visibility else name)
            item.setSizeHint(SpaceCardDelegate.SIZE)
            view.addItem(item)
        self.selection_total.setVisible(True)
        self.selection_total.setText(
            translate_text("{pages} páginas selecionadas em {spaces} de {total} espaços desta fonte.").format(
                pages=total_selected, spaces=spaces_with_selection, total=len(containers)
            )
        )
        self._filter_selection_space_cards()

    def _filter_selection_space_cards(self, text: str | None = None) -> None:
        if not hasattr(self, "selection_space_search"):
            return
        query = (text if text is not None else self.selection_space_search.text()).strip().casefold()
        view = self.selection_spaces
        for row in range(view.count()):
            item = view.item(row)
            name = str(item.data(SpaceCardDelegate.NAME_ROLE) or "")
            item.setHidden(bool(query) and query not in name.casefold())

    def _mark_whole_space(self, container_id: str, selected: bool) -> None:
        """Select or clear every page of a space, loading it first when needed."""
        source = self._selection_source()
        data = self.trees.get(source.id) if source else None
        if source is None or data is None:
            return
        complete = self._container_loaded(source, data, container_id) and not self._container_requires_full_load(
            data, container_id
        )
        if not selected or complete:
            self._set_space_selection(source, container_id, selected)
            return
        if self.worker is not None:
            self.statusBar().showMessage(translate_text("Aguarde a operação atual terminar…"), 4000)
            self._refresh_selection_home()
            return
        self._load_container_for_source(
            source,
            container_id,
            target="selection",
            load_all=True,
            on_loaded=lambda: self._set_space_selection(source, container_id, True),
        )

    def _set_space_selection(self, source: SourceConfig, container_id: str, selected: bool) -> None:
        data = self.trees.get(source.id, {})
        store = SelectionStore.from_selections(self.project.selections)
        if selected:
            for page in self._tree_pages(data, container_id):
                page_id = str(page.get("id") or "")
                if page_id and self._page_container_id(source, page) == container_id:
                    store.set(source.id, container_id, page_id, True)
        else:
            for item in store.selections():
                if item.source_id == source.id and item.container_id == container_id:
                    store.set(source.id, container_id, item.document_id, False)
        self._commit_selection_store(store)
        self._flush_selection_state()
        self._refresh_selection_home()

    def _toggle_page_id_column(self) -> None:
        self.selection_tree.setColumnHidden(1, not self.selection_tree.isColumnHidden(1))

    def _selection_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE):
            self._preview_tree_item(item)

    def _selection_context_menu(self, position: Any) -> None:
        item = self.selection_tree.itemAt(position)
        if item is None or not item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE):
            return
        menu = QMenu(self)
        menu.addAction(
            translate_text("👁 Prévia do Markdown desta página"), lambda: self._preview_tree_item(item)
        )
        menu.exec(self.selection_tree.viewport().mapToGlobal(position))

    def _preview_tree_item(self, item: QTreeWidgetItem) -> None:
        source = self._selection_source()
        if source is None:
            return
        self._preview_real_page(
            source,
            str(item.data(0, VisibilityBadgeDelegate.CONTAINER_ROLE) or ""),
            str(item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE) or ""),
            str(item.data(0, VisibilityBadgeDelegate.TITLE_ROLE) or ""),
        )

    def _open_selection_container(self, container_id: str) -> None:
        source = self._selection_source()
        data = self.trees.get(source.id) if source else None
        if not source or data is None:
            return
        if self.worker is not None:
            self.statusBar().showMessage(
                translate_text("Aguarde a operação atual terminar…"), 4000
            )
            return
        self._active_selection_container = container_id
        container = next(
            (item for item in self._selection_containers(source) if item["id"] == container_id),
            {"name": container_id},
        )
        self.selection_space_title.setText(str(container["name"]))
        self.selection_stack.setCurrentIndex(1)
        self._update_load_context()
        self.selection_search.clear()
        self.selection_filter.setCurrentIndex(0)
        if self._container_loaded(source, data, str(container_id)) and not self._container_requires_full_load(
            data, str(container_id)
        ):
            self._populate_selection_tree(source, data, container_id=container_id)
            return
        self.selection_tree.clear()
        self.selection_count.setText(translate_text("Carregando páginas deste espaço…"))
        self._load_container_for_source(
            source, str(container_id), target="selection", load_all=True
        )



    def _selection_go_back(self) -> None:
        self._active_selection_container = None
        self.selection_stack.setCurrentIndex(0)
        self._update_load_context()
        self._refresh_selection_home()


    def _selection_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        self._load_expanded_document(item, target="selection")
















    def _flush_selection_state(self) -> None:
        """Refresh visual summaries once after the store is reconciled."""
        self._update_selection_count()
        # Only rebuild container cards when the home view is active; the detail
        # tree already reflects the new selection state and needs no rebuild.
        if not hasattr(self, "selection_stack") or self.selection_stack.currentIndex() == 0:
            self._refresh_selection_home()
        self.mark_dirty()

    def _commit_selection_store(self, store: SelectionStore) -> None:
        # project.selections is the source of truth; the store and the legacy
        # selected_page_ids (kept for older project files and counters) are
        # derived here, the only place the window writes selection state.
        self.project.selections = store.selections()
        self.selection_store = store
        for source in self.project.sources:
            source.selected_page_ids = sorted(
                item.document_id
                for item in store.selections()
                if item.source_id == source.id
            )


    def _update_selection_count(self) -> None:
        leaves = self._leaf_items()
        source = self._selection_source()
        data = self.trees.get(source.id) if source else None
        if source and data:
            checked = len(self.project.selected_keys_for(source.id))
            total = len(self._tree_pages(data))
        else:
            checked = sum(item.checkState(0) == Qt.CheckState.Checked for item in leaves)
            total = len(leaves)
        visible = sum(not item.isHidden() for item in leaves)
        self.selection_count.setText(
            translate_text(
                "… {checked} de {total} páginas carregadas selecionadas · {visible} visíveis"
            ).format(checked=checked, total=total, visible=visible)
        )
        self._update_extraction_summary()




    def _document_items(self) -> list[QTreeWidgetItem]:
        """Return every rendered document, including nodes with children."""
        result: list[QTreeWidgetItem] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE):
                result.append(item)
            for index in range(item.childCount()):
                child = item.child(index)
                if child is not None:
                    walk(child)

        for index in range(self.selection_tree.topLevelItemCount()):
            item = self.selection_tree.topLevelItem(index)
            if item is not None:
                walk(item)
        return result

    def _recompute_parent_check_states(self) -> None:
        """Recompute parent states once after a batch change."""
        def walk(item: QTreeWidgetItem) -> None:
            for index in range(item.childCount()):
                child = item.child(index)
                if child is not None:
                    walk(child)
            if item.childCount() == 0:
                return
            states = [
                child.checkState(0)
                for index in range(item.childCount())
                if (child := item.child(index)) is not None
            ]
            if states and all(state == Qt.CheckState.Checked for state in states):
                state = Qt.CheckState.Checked
            elif states and all(state == Qt.CheckState.Unchecked for state in states):
                state = Qt.CheckState.Unchecked
            else:
                state = Qt.CheckState.PartiallyChecked
            item.setCheckState(0, state)

        for index in range(self.selection_tree.topLevelItemCount()):
            item = self.selection_tree.topLevelItem(index)
            if item is not None:
                walk(item)

    def _populate_selection_tree(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        *,
        container_id: str | None = None,
    ) -> None:
        """Render one item per real page and preserve selection in one pass."""
        blocker = QSignalBlocker(self.selection_tree)
        self.selection_tree.setSortingEnabled(False)
        self.selection_tree.clear()

        all_pages = ordered_pages(self._tree_pages(data, container_id))
        if container_id is not None:
            all_pages = [
                page
                for page in all_pages
                if self._page_container_id(source, page) == str(container_id)
            ]
        render_key = self._page_render_key(source, container_id or "")
        limit = self._selection_render_limits.get(render_key, 800)
        pages = all_pages[:limit]
        page_ids = {str(page.get("id") or "") for page in pages}
        parent_ids = parent_ids_in_list(pages)
        root_id = str((data.get("root") or {}).get("id") or "")
        document_nodes: dict[str, QTreeWidgetItem] = {}
        parent_by_page: dict[str, str | None] = {}

        def ancestor_chain(page: dict[str, Any]) -> list[dict[str, Any]]:
            ancestors = [
                item for item in (page.get("ancestors") or [])
                if isinstance(item, dict)
            ]
            ancestor_ids = [str(item.get("id") or "") for item in ancestors]
            if root_id and root_id in ancestor_ids:
                ancestors = ancestors[ancestor_ids.index(root_id) + 1 :]
            return ancestors

        for page in pages:
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            parent_by_page[page_id] = page_parent_id(page, page_ids)
            ancestor_titles = [
                str(item.get("title") or "")
                for item in ancestor_chain(page)
                if item.get("title")
            ]
            if not ancestor_titles and page.get("path") and isinstance(page.get("path"), list):
                raw_path = [str(p) for p in page["path"] if p]
                if len(raw_path) > 1:
                    ancestor_titles = raw_path[:-1]
            version = page.get("version", {}) or {}
            title = str(page.get("title") or "Sem titulo")
            path = " > ".join(ancestor_titles)
            page_container_id = self._page_container_id(source, page)
            selected = self.selection_store.is_selected(
                source.id, page_container_id, page_id
            )
            state_text = "Selecionada" if selected else "Nao extraida"
            item = SortableTreeItem(
                [
                    title,
                    page_id,
                    path,
                    relative_timestamp(str(version.get("when") or "")),
                    state_text,
                ]
            )
            item.setToolTip(3, display_timestamp(str(version.get("when") or "")))
            sort_values = [
                title.casefold(),
                int(page_id) if page_id.isdigit() else page_id,
                path.casefold(),
                timestamp_sort_value(str(version.get("when") or "")),
                state_text.casefold(),
            ]
            for column, value in enumerate(sort_values):
                item.setData(column, SortableTreeItem.SORT_ROLE, value)
            visibility, visibility_kind = self._page_visibility(source, page)
            # Public is the usual case; only restricted/unknown pages get a badge.
            item.setData(
                0, VisibilityBadgeDelegate.VISIBILITY_ROLE, "" if visibility_kind == "public" else visibility
            )
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE, visibility_kind)
            item.setData(0, VisibilityBadgeDelegate.TITLE_ROLE, title)
            sel_icon = "📁" if (page_id in parent_ids or bool(page.get("has_children"))) else "📄"
            item.setText(0, f"{sel_icon} {title}")
            item.setData(0, VisibilityBadgeDelegate.ICON_ROLE, sel_icon)
            item.setData(0, VisibilityBadgeDelegate.SOURCE_ROLE, source.id)
            item.setData(0, VisibilityBadgeDelegate.CONTAINER_ROLE, page_container_id)
            item.setData(0, VisibilityBadgeDelegate.DOCUMENT_ROLE, page_id)
            item.setData(0, Qt.ItemDataRole.UserRole, source.id)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, page_container_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked,
            )
            document_nodes[page_id] = item

            lazy_state = self._lazy_state(data, page_container_id)
            # Raizes (sem parent_id) sao conservadoramente expansiveis quando o
            # endpoint de raizes omite metadados de filhos, alinhando-se com a
            # arvore de extracao (_populate_page_tree_lazy). Expandir ainda faz
            # a solicitacao de filhos sob demanda; nenhum descendente e buscado
            # previamente aqui.
            if (
                lazy_state.get("enabled")
                and (not page.get("parent_id") or bool(page.get("has_children")))
                and page_id not in {str(value) for value in lazy_state.get("loaded_parents", [])}
            ):
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

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
                parent_node: QTreeWidgetItem | None = hierarchy_nodes.get(ancestor_id)
                if parent_node is None:
                    parent_node = SortableTreeItem(
                        [
                            f"📁 {ancestor_title}",
                            ancestor_id,
                            " > ".join(accumulated_titles),
                            "",
                            "",
                        ]
                    )
                    parent_node.setFlags(
                        parent_node.flags()
                        | Qt.ItemFlag.ItemIsUserCheckable
                        | Qt.ItemFlag.ItemIsAutoTristate
                    )
                    parent_node.setCheckState(0, Qt.CheckState.Unchecked)
                    parent_node.setData(0, VisibilityBadgeDelegate.TITLE_ROLE, ancestor_title)
                    parent_node.setData(0, VisibilityBadgeDelegate.ICON_ROLE, "📁")
                    parent_node.setData(0, VisibilityBadgeDelegate.VISIBILITY_ROLE, "Pasta")
                    parent_node.setData(0, VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE, "folder")
                    if anchor is None:
                        self.selection_tree.addTopLevelItem(parent_node)
                    else:
                        anchor.addChild(parent_node)
                    hierarchy_nodes[ancestor_id] = parent_node
                anchor = parent_node
            parent = anchor or hierarchy_nodes.get(parent_by_page.get(page_id) or "")
            if parent is None:
                self.selection_tree.addTopLevelItem(document_item)
            else:
                parent.addChild(document_item)

        self._recompute_parent_check_states()
        # Preserve the provider order after repopulating: clear the active
        # sort column with setSortIndicator(-1, ...) instead of toggling
        # setSortingEnabled, which would also hide the indicator and disable
        # header clicks on some Qt versions.
        self.selection_tree.setSortingEnabled(False)
        self.selection_tree.setProperty("_alquimista_sort_column", -1)
        self.selection_tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = self.selection_tree.header()
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
        del blocker
        lazy_container_state = (
            self._lazy_state(data, container_id) if container_id else {}
        )
        if not lazy_container_state.get("enabled"):
            self.selection_tree.expandToDepth(1)
        self._update_selection_count()
        self.selection_render_status.setText(
            translate_text(
                "Mostrando {visible:,} de {total:,} páginas. "
                "Use a pesquisa ou carregue mais para navegar pelo restante."
            ).format(visible=len(pages), total=len(all_pages))
        )
        self.selection_load_more_button.setVisible(len(pages) < len(all_pages))
        if container_id is None and hasattr(self, "selection_home_layout"):
            self._refresh_selection_home()

    def _leaf_items(self) -> list[QTreeWidgetItem]:
        """Compatibility alias; all document nodes are selectable."""
        return self._document_items()

    def _set_selection(self, state: Qt.CheckState, *, visible_only: bool = False) -> None:
        blocker = QSignalBlocker(self.selection_tree)
        target = state == Qt.CheckState.Checked
        for item in self._document_items():
            if not visible_only or not item.isHidden():
                item.setCheckState(0, Qt.CheckState.Checked if target else Qt.CheckState.Unchecked)
        self._recompute_parent_check_states()
        del blocker
        if not visible_only:
            source = self._selection_source()
            data = self.trees.get(source.id) if source else None
            if source and data is not None:
                store = SelectionStore.from_selections(self.project.selections)
                for page in self._tree_pages(data, self._active_selection_container):
                    container_id = self._page_container_id(source, page)
                    document_id = str(page.get("id") or "")
                    if container_id and document_id:
                        store.set(source.id, container_id, document_id, target)
                self._commit_selection_store(store)
        self._apply_selection_state()
        self._flush_selection_state()

    def _invert_selection(self) -> None:
        blocker = QSignalBlocker(self.selection_tree)
        for item in self._document_items():
            if not item.isHidden():
                item.setCheckState(
                    0,
                    Qt.CheckState.Unchecked
                    if item.checkState(0) == Qt.CheckState.Checked
                    else Qt.CheckState.Checked,
                )
        self._recompute_parent_check_states()
        del blocker
        self._apply_selection_state()
        self._flush_selection_state()

    def _selection_changed(self, item: QTreeWidgetItem | None = None, *_args: Any) -> None:
        """Apply one user event, propagating descendants in a single batch."""
        if getattr(self, "_selection_changing", False):
            return
        self._selection_changing = True
        try:
            blocker = QSignalBlocker(self.selection_tree)
            if item is not None and item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE):
                if item.childCount():
                    target = (
                        Qt.CheckState.Unchecked
                        if item.checkState(0) == Qt.CheckState.Unchecked
                        else Qt.CheckState.Checked
                    )
                    stack = [item.child(index) for index in range(item.childCount())]
                    while stack:
                        child = stack.pop()
                        if child is None:
                            continue
                        if child.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE):
                            child.setCheckState(0, target)
                        stack.extend(
                            child.child(index) for index in range(child.childCount())
                        )
            self._recompute_parent_check_states()
            del blocker
            self._apply_selection_state()
            self._flush_selection_state()
        finally:
            self._selection_changing = False

    def _apply_selection_state(self) -> None:
        """Reconcile all rendered documents with the canonical store once."""
        store = SelectionStore.from_selections(self.project.selections)
        source_ids = {str(src.id) for src in self.project.sources}
        for item in self._document_items():
            source_id = str(item.data(0, VisibilityBadgeDelegate.SOURCE_ROLE) or "")
            container_id = str(item.data(0, VisibilityBadgeDelegate.CONTAINER_ROLE) or "")
            document_id = str(item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE) or "")
            if source_id in source_ids and container_id and document_id:
                store.set(
                    source_id,
                    container_id,
                    document_id,
                    item.checkState(0) == Qt.CheckState.Checked,
                )
        self._commit_selection_store(store)

    def _filter_selection(self, *_args: Any) -> None:
        query = self.selection_search.text().strip().casefold()
        mode = str(self.selection_filter.currentData() or "all")

        def walk(item: QTreeWidgetItem) -> bool:
            child_visible = any(
                walk(child) for i in range(item.childCount()) if (child := item.child(i)) is not None
            )
            is_document = bool(item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE))
            text_match = not query or query in " ".join(
                item.text(i) for i in range(item.columnCount())
            ).casefold()
            visibility_kind = str(
                item.data(0, VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE) or "unknown"
            )
            state_match = (
                mode == "all"
                or (mode == "selected" and item.checkState(0) == Qt.CheckState.Checked)
                or (mode == "unselected" and item.checkState(0) != Qt.CheckState.Checked)
                or (mode == "public" and visibility_kind == "public")
                or (mode == "private" and visibility_kind == "private")
                or (mode == "unknown" and visibility_kind == "unknown")
            )
            own = is_document and text_match and state_match
            visible = own or child_visible
            item.setHidden(not visible)
            if child_visible:
                item.setExpanded(True)
            return visible

        for index in range(self.selection_tree.topLevelItemCount()):
            item = self.selection_tree.topLevelItem(index)
            if item is not None:
                walk(item)
        self._update_selection_count()
