from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QStackedWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ...models import SourceConfig
from ..components import (
    HorizontalScrollArea,
    SourceCard,
    VisibilityBadgeDelegate,
    button,
    card,
    page_header,
)
from ..controllers import TreeController
from ..i18n import translate_text
from ..tree_models import (
    page_container_id as tree_page_container_id,
)
from ..tree_models import (
    tree_containers,
    tree_pages,
)
from . import WindowBase


class PagesBrowserMixin(WindowBase):
    """The Pages view: space cards, page tables, paging and column layout."""

    # Attributes and methods provided by MainWindow or sibling mixins.
    _page_render_limits: dict[tuple[str, str], int]
    _active_page_container: str | None
    _active_selection_container: str | None
    _cancel_tree_operation: Any
    _container_visibility: Any
    _lazy_state: Any
    _load_container_for_source: Any
    _page_tree_item_expanded: Any
    _populate_page_tree: Any
    _populate_selection_tree: Any
    _selection_render_limits: Any
    _selection_source: Any
    _tree_source_changed: Any
    _update_load_context: Any
    load_tree: Any
    selection_cards_scroll: Any
    selection_store: Any
    source_by_combo: Any
    test_connection: Any
    tree_controller: Any
    trees: Any
    worker: Any

    def _configure_data_tree(
        self, tree: QTreeWidget, widths: list[int], settings_key: str
    ) -> None:
        self.tree_controller.configure_data_tree(tree, widths, settings_key)

    def _sort_tree_by_column(self, tree: QTreeWidget, column: int) -> None:
        self.tree_controller.sort_tree_by_column(tree, column)

    def _finalize_tree_sort(
        self, tree: QTreeWidget, column: int, order: Qt.SortOrder
    ) -> None:
        self.tree_controller.finalize_tree_sort(tree, column, order)

    def _restore_table_columns(
        self, tree: QTreeWidget, widths: list[int], settings_key: str
    ) -> None:
        self.tree_controller.restore_table_columns(tree, widths, settings_key)

    def _move_page_column(self, direction: int) -> None:
        self.tree_controller.move_page_column(
            self.page_column_choice, self.page_tree, direction
        )

    def _send_page_column(self, to_end: bool) -> None:
        self.tree_controller.send_page_column(
            self.page_column_choice, self.page_tree, to_end
        )

    def _pages_page(self) -> QWidget:
        page, layout = page_header(
            "Espaços e páginas",
            "Localize, organize e confira o conteúdo disponível na fonte selecionada.",
            "🌳",
        )
        self._active_page_container = None
        self._page_container_cards: dict[str, SourceCard] = {}
        tools = QHBoxLayout()
        self.tree_source = QComboBox()
        self.tree_source.currentIndexChanged.connect(self._tree_source_changed)
        tools.addWidget(QLabel("Fonte"))
        tools.addWidget(self.tree_source, 1)
        tools.addWidget(button("🔌 Testar", self.test_connection))
        self.tree_load_button = button(
            "🌳 Carregar espaços", self.load_tree, primary=True
        )
        tools.addWidget(self.tree_load_button)
        self.tree_cancel_button = button(
            "Cancelar", self._cancel_tree_operation, danger=True
        )
        self.tree_cancel_button.setEnabled(False)
        tools.addWidget(self.tree_cancel_button)
        self.tree_load_status = QLabel("Pronto para carregar a árvore.")
        self.tree_load_status.setObjectName("subtitle")
        tools.addWidget(self.tree_load_status)
        self.tree_load_progress = QProgressBar()
        self.tree_load_progress.setRange(0, 0)
        self.tree_load_progress.setTextVisible(False)
        self.tree_load_progress.setFixedWidth(150)
        self.tree_load_progress.setVisible(False)
        tools.addWidget(self.tree_load_progress)
        layout.addLayout(tools)

        self.pages_stack = QStackedWidget()

        home = QWidget()
        self.page_home_layout = QVBoxLayout(home)
        self.page_home_layout.setContentsMargins(0, 4, 0, 0)
        self.page_home_empty = QLabel(
            "🌳 Carregue os espaços disponíveis para escolher qual conteúdo visualizar."
        )
        self.page_home_empty.setObjectName("subtitle")
        self.page_home_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_home_empty.setWordWrap(True)
        self.page_home_layout.addWidget(self.page_home_empty, 1)
        self.page_space_search = QLineEdit()
        self.page_space_search.setPlaceholderText(
            "🔎 Pesquisar por nome do espaço…"
        )
        self.page_space_search.setClearButtonEnabled(True)
        self.page_space_search.textChanged.connect(self._filter_page_space_cards)
        self.page_home_layout.addWidget(self.page_space_search)
        self.page_cards_scroll = HorizontalScrollArea()
        self.page_cards_scroll.setObjectName("spaceCardsScroll")
        self.page_cards_scroll.setWidgetResizable(True)
        self.page_cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page_cards_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.page_cards_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        page_cards_host = QWidget()
        self.page_cards_layout = QGridLayout(page_cards_host)
        self.page_cards_layout.setContentsMargins(8, 12, 8, 16)
        self.page_cards_layout.setHorizontalSpacing(16)
        self.page_cards_layout.setVerticalSpacing(16)
        self.page_cards_scroll.setWidget(page_cards_host)
        self.page_home_layout.addWidget(self.page_cards_scroll, 1)
        self.page_cards_scroll.setVisible(False)
        self.pages_stack.addWidget(home)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        detail_tools = QHBoxLayout()
        self.page_back_button = button(
            "← Voltar aos espaços", self._page_go_back
        )
        detail_tools.addWidget(self.page_back_button)
        self.page_space_title = QLabel("Espaço selecionado")
        self.page_space_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        detail_tools.addWidget(self.page_space_title)
        detail_tools.addStretch()
        detail_layout.addLayout(detail_tools)

        page_headers = [
            "Título",
            "Tipo",
            "Page ID",
            "Módulo",
            "Caminho",
            "Versão",
            "Atualização",
        ]
        self.page_column_choice = QComboBox()
        for logical, title in enumerate(page_headers):
            self.page_column_choice.addItem(title, logical)
        self.page_column_choice.setAccessibleName(
            "Coluna que será movimentada"
        )
        self.page_column_choice.setVisible(False)

        summary, summary_layout = card()
        summary.setObjectName("pageSummaryCard")
        summary_row = QHBoxLayout()
        self.page_space_stat = self._page_stat("🌳", "Espaço selecionado", "—")
        self.page_count_stat = self._page_stat("📄", "Páginas", "0")
        self.page_sync_stat = self._page_stat(
            "⟳", "Última sincronização", "Ainda não"
        )
        summary_row.addWidget(self.page_space_stat)
        summary_row.addWidget(self.page_count_stat)
        summary_row.addWidget(self.page_sync_stat)
        summary_row.addStretch()
        summary_layout.addLayout(summary_row)
        detail_layout.addWidget(summary)

        table_card, table_layout = card()
        table_card.setObjectName("pageTableCard")
        self.page_tree: QTreeWidget = QTreeWidget()
        self.page_tree.setColumnCount(7)
        self.page_tree.setHeaderLabels(page_headers)
        self._configure_data_tree(
            self.page_tree, [250, 75, 90, 120, 250, 65, 130], "pages"
        )
        self.page_tree.setAlternatingRowColors(True)
        self.page_tree.setUniformRowHeights(True)
        self.page_tree.setItemDelegateForColumn(
            0, VisibilityBadgeDelegate(self.page_tree)
        )
        self.page_tree.itemExpanded.connect(self._page_tree_item_expanded)
        table_layout.addWidget(self.page_tree, 1)
        self.tree_empty = QLabel("🌱 Carregue uma árvore para começar.")
        self.tree_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tree_empty.setObjectName("subtitle")
        table_layout.addWidget(self.tree_empty)
        guidance = QLabel(
            "¦ Dica: arraste os títulos das colunas para reorganizar a visualização "
            "ou clique em um título para ordenar os itens."
        )
        guidance.setObjectName("subtitle")
        guidance.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_layout.addWidget(guidance)
        page_render_tools = QHBoxLayout()
        self.page_render_status = QLabel("Nenhum espaço carregado")
        self.page_render_status.setObjectName("subtitle")
        page_render_tools.addWidget(self.page_render_status, 1)
        self.page_load_more_button = button(
            "Carregar mais páginas", self._load_more_page_rows
        )
        self.page_load_more_button.setVisible(False)
        page_render_tools.addWidget(self.page_load_more_button)
        detail_layout.addLayout(page_render_tools)
        detail_layout.addWidget(table_card, 1)
        self.pages_stack.addWidget(detail)
        layout.addWidget(self.pages_stack, 1)
        return page

    def _page_stat(self, icon: str, label: str, value: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pageStat")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 10, 14, 10)
        icon_label = QLabel(icon)
        icon_label.setObjectName("pageStatIcon")
        icon_label.setStyleSheet("font-size: 18pt;")
        row.addWidget(icon_label)
        text = QVBoxLayout()
        value_label = QLabel(value)
        value_label.setObjectName("pageStatValue")
        value_label.setStyleSheet("font-size: 12pt; font-weight: 700;")
        value_label.setProperty("stat_value", True)
        text.addWidget(value_label)
        label_widget = QLabel(label)
        label_widget.setObjectName("subtitle")
        text.addWidget(label_widget)
        row.addLayout(text)
        return frame

    def _set_page_stat(self, frame: QFrame, value: str) -> None:
        for label in frame.findChildren(QLabel):
            if label.property("stat_value") is True:
                label.setText(value)
                return

    def _refresh_page_summary(
        self, source: SourceConfig | None, data: dict[str, Any] | None = None
    ) -> None:
        if not hasattr(self, "page_space_stat"):
            return
        if not source:
            self._set_page_stat(self.page_space_stat, "—")
            self._set_page_stat(self.page_count_stat, "0")
            self._set_page_stat(
                self.page_sync_stat, translate_text("Ainda não")
            )
            return
        root = (data or {}).get("root", {}) or {}
        space_name = (
            source.space_name
            or source.space_key
            or str(root.get("title") or "—")
        )
        count = str(len((data or {}).get("pages", []) or []))
        loaded_at = str((data or {}).get("loaded_at") or "")
        if loaded_at:
            try:
                sync_label = (
                    datetime.fromisoformat(loaded_at.replace("Z", "+00:00"))
                    .astimezone()
                    .strftime("%d/%m/%Y %H:%M")
                )
            except ValueError:
                sync_label = loaded_at
        else:
            sync_label = translate_text("Ainda não")
        self._set_page_stat(self.page_space_stat, space_name)
        self._set_page_stat(self.page_count_stat, count)
        self._set_page_stat(self.page_sync_stat, sync_label)

    @staticmethod
    def _page_container_id(source: SourceConfig, page: dict[str, Any]) -> str:
        return tree_page_container_id(source, page)

    def _tree_pages(
        self, data: dict[str, Any], container_id: str | None = None
    ) -> list[dict[str, Any]]:
        return tree_pages(data, container_id)

    def _tree_containers(
        self, source: SourceConfig, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return tree_containers(source, data)

    def _container_loaded(
        self, source: SourceConfig, data: dict[str, Any], container_id: str
    ) -> bool:
        if str(container_id) in (data.get("pages_by_container") or {}):
            return True
        return any(
            self._page_container_id(source, page) == str(container_id)
            for page in data.get("pages", []) or []
        )

    @staticmethod
    def _container_requires_full_load(
        data: dict[str, Any], container_id: str
    ) -> bool:
        """Return whether the current snapshot contains roots only."""
        state = (
            (data.get("lazy_discovery") or {}).get(str(container_id), {})
            or {}
        )
        return bool(
            state.get("enabled") and not state.get("inventory_complete")
        )

    def _selection_containers(
        self, source: SourceConfig
    ) -> list[dict[str, Any]]:
        data = self.trees.get(source.id) or {}
        result = self._tree_containers(source, data)
        loaded_pages = data.get("pages_by_container") or {}
        for container in result:
            container_id = str(container["id"])
            container["pages"] = int(
                container.get("page_count")
                or len(loaded_pages.get(container_id, []) or [])
            )
            container["loaded"] = container_id in loaded_pages or bool(
                any(
                    self._page_container_id(source, page) == container_id
                    for page in data.get("pages", []) or []
                )
            )
        counts = self.selection_store.count_by_container(source.id)
        for container in result:
            container["selected"] = counts.get((source.id, container["id"]), 0)
        load_order = {
            str(container_id): index
            for index, container_id in enumerate(loaded_pages)
        }
        original_order = {
            str(container["id"]): index for index, container in enumerate(result)
        }
        return sorted(
            result,
            key=lambda container: (
                not bool(container.get("loaded")),
                load_order.get(str(container["id"]), len(load_order)),
                original_order[str(container["id"])],
            ),
        )

    def _refresh_pages_home(self) -> None:
        if not hasattr(self, "page_home_layout"):
            return
        while self.page_cards_layout.count():
            item = self.page_cards_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._page_container_cards.clear()
        source = self.source_by_combo(
            getattr(
                self,
                "tree_source",
                getattr(self, "selection_source", None),
            )
        )
        data = self.trees.get(source.id) if source else None
        containers = (
            self._tree_containers(source, data or {}) if source else []
        )
        if not containers:
            self.page_home_empty.setVisible(True)
            self.page_space_search.setVisible(False)
            self.page_cards_scroll.setVisible(False)
            return
        if source is None:
            return
        self.page_home_empty.setVisible(False)
        self.page_space_search.setVisible(True)
        self.page_cards_scroll.setVisible(True)

        accents = ["#7FE4B5", "#B09AFF", "#67B7FF", "#75E7BA", "#A995F4"]
        for index, container in enumerate(containers):
            container_id = str(container["id"])
            loaded = bool(container.get("loaded")) or container_id in (
                data or {}
            ).get("pages_by_container", {})
            count = (
                len(self._tree_pages(data or {}, container_id))
                if loaded
                else int(container.get("page_count", 0) or 0)
            )
            subtitle = (
                f"{count} páginas carregadas"
                if loaded
                else "Clique para carregar as páginas"
            )
            visibility, visibility_kind = self._container_visibility(
                source, data or {}, container
            )
            card = SourceCard(
                container_id,
                str(container["name"]),
                subtitle,
                3,
                accents[index % len(accents)],
                visibility=visibility,
                visibility_kind=visibility_kind,
            )
            card.setFixedWidth(300)
            card.setProperty("container_name", str(container["name"]))
            card.clicked.connect(self._open_page_container)
            self._page_container_cards[container_id] = card
            row = index % 2
            column = index // 2
            self.page_cards_layout.addWidget(card, row, column)
        self._filter_page_space_cards()

    def _filter_page_space_cards(self, text: str | None = None) -> None:
        if not hasattr(self, "page_space_search"):
            return
        query = (
            text if text is not None else self.page_space_search.text()
        ).strip().casefold()
        self._reflow_space_cards(
            self.page_cards_layout, self._page_container_cards, query
        )

    def _open_page_container(self, container_id: str) -> None:
        source = self.source_by_combo(
            getattr(
                self,
                "tree_source",
                getattr(self, "selection_source", None),
            )
        )
        data = self.trees.get(source.id) if source else None
        if not source or data is None:
            return
        if self.worker is not None:
            self.tree_load_status.setText(
                translate_text("Aguarde a operação atual terminar…")
            )
            return
        self._active_page_container = str(container_id)
        container = next(
            (
                item
                for item in self._tree_containers(source, data)
                if item["id"] == str(container_id)
            ),
            {"id": container_id, "name": container_id},
        )
        self.page_space_title.setText(f"🗂  {container['name']}")
        if hasattr(self, "pages_stack"):
            self.pages_stack.setCurrentIndex(1)
        self._update_load_context()
        if self._container_loaded(
            source, data, str(container_id)
        ) and not self._container_requires_full_load(
            data, str(container_id)
        ):
            self._populate_page_tree(
                source, data, container_id=str(container_id)
            )
            self._refresh_page_summary(
                source,
                {
                    **data,
                    "pages": self._tree_pages(data, str(container_id)),
                },
            )
            return
        self._load_container_for_source(
            source, str(container_id), target="pages", load_all=True
        )

    def _page_go_back(self) -> None:
        self._active_page_container = None
        if hasattr(self, "pages_stack"):
            self.pages_stack.setCurrentIndex(0)
        self._update_load_context()
        self._refresh_pages_home()

    def _page_render_key(
        self, source: SourceConfig, container_id: str
    ) -> tuple[str, str]:
        return TreeController.page_render_key(source.id, str(container_id))

    def _load_more_page_rows(self) -> None:
        source = self.source_by_combo(
            getattr(
                self,
                "tree_source",
                getattr(self, "selection_source", None),
            )
        )
        if not source or not self._active_page_container:
            return
        data = self.trees.get(source.id)
        lazy = (
            self._lazy_state(data or {}, self._active_page_container)
            if data
            else {}
        )
        if lazy.get("enabled") and lazy.get("next_cursor"):
            self._load_container_for_source(
                source,
                self._active_page_container,
                target="pages",
                load_all=False,
                cursor=str(lazy["next_cursor"]),
            )
            return
        key = self._page_render_key(source, self._active_page_container)
        self._page_render_limits[key] = (
            self._page_render_limits.get(key, 800) + 800
        )
        if data:
            self._populate_page_tree(
                source, data, container_id=self._active_page_container
            )

    def _load_more_selection_rows(self) -> None:
        source = self._selection_source()
        if not source or not self._active_selection_container:
            return
        data = self.trees.get(source.id)
        lazy = (
            self._lazy_state(data or {}, self._active_selection_container)
            if data
            else {}
        )
        if lazy.get("enabled") and lazy.get("next_cursor"):
            self._load_container_for_source(
                source,
                self._active_selection_container,
                target="selection",
                load_all=False,
                cursor=str(lazy["next_cursor"]),
            )
            return
        key = self._page_render_key(source, self._active_selection_container)
        self._selection_render_limits[key] = (
            self._selection_render_limits.get(key, 800) + 800
        )
        if data:
            self._populate_selection_tree(
                source,
                data,
                container_id=self._active_selection_container,
            )

    def _reflow_space_cards(
        self,
        layout: QGridLayout,
        cards: dict[str, SourceCard],
        query: str,
    ) -> None:
        scroll = None
        if layout is getattr(self, "page_cards_layout", None):
            scroll = self.page_cards_scroll
        elif layout is getattr(self, "selection_cards_layout", None):
            scroll = self.selection_cards_scroll
        self.tree_controller.reflow_space_cards(
            layout, cards, query, scroll_area=scroll
        )
