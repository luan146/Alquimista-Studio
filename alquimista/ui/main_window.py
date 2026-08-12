from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import (
    QPropertyAnimation,
    QSignalBlocker,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QCloseEvent, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..browser import BrowserCache, LazyDiscoveryService
from ..browser.adapters import ConnectorDiscoveryAdapter
from ..client import ConfluenceClient, session_directory
from ..connectors import default_registry
from ..logging_utils import configure_logging, default_log_path
from ..markdown import MarkdownTransformer, page_metadata, sample_page, sha256_text
from ..models import (
    AuthMode,
    MarkdownOptions,
    ProjectConfig,
    SourceConfig,
    default_project,
    now_iso,
)
from ..runtime import CancellationToken
from ..selection import SelectionStore
from ..services import ConsolidationService, SourceRuntime
from ..storage import MANIFEST_NAME
from .components import (
    APP_TITLE,
    NAV_ICON_INDEX,
    NAVIGATION,
    AlchemistIconAtlas,
    HorizontalScrollArea,
    ResponsiveOutputControls,
    SortableTreeItem,
    SourceCard,
    VisibilityBadgeDelegate,
    button,
    card,
    page_header,
    timestamp_sort_value,
)
from .controllers import RuntimeSecrets
from .execution_controller import (
    execute_selected_operation,
    prepare_runtimes,
    retry_failures,
    run_complete,
    run_extraction,
    validated_project_snapshot,
)
from .i18n import (
    LANGUAGE_NAMES,
    LanguageManager,
    create_settings,
    retranslate_widget_tree,
    translate_text,
)
from .mixins.connection_mixin import ConnectionMixin
from .mixins.selection_mixin import SelectionMixin
from .mixins.source_mixin import SourceMixin
from .operation_controller import WorkerOperationController
from .pages.connection_page import build_connection_page
from .pages.consolidation_page import build_consolidation_page
from .pages.dashboard_page import build_dashboard_page
from .pages.extraction_page import build_extraction_page
from .pages.markdown_page import build_markdown_page
from .pages.results_page import build_results_page
from .pages.review_page import build_review_page
from .pages.selection_page import build_selection_page
from .pages.sources_page import build_sources_page
from .project_controller import (
    load_project_file,
    resolve_project_dir,
    save_project_file,
)
from .state import MainWindowState
from .theme import apply_theme
from .tree_models import (
    explicit_visibility_kind,
    ordered_pages,
    page_parent_id,
    parent_ids_in_list,
    tree_containers,
    tree_pages,
    visibility_for_container,
    visibility_for_page,
)
from .tree_models import (
    lazy_state as tree_lazy_state,
)
from .tree_models import (
    page_container_id as tree_page_container_id,
)
from .workers import Worker


class MainWindow(ConnectionMixin, SourceMixin, SelectionMixin, QMainWindow):
    def __init__(
        self,
        mode: str = "complete",
        language_manager: LanguageManager | None = None,
    ) -> None:
        super().__init__()
        # Os antigos lançadores "extrator" e "consolidador" continuam aceitos
        # apenas por compatibilidade com scripts existentes. A interface sempre
        # abre o fluxo completo e a operação é escolhida dentro da tela.
        self.mode = "complete"
        self.project = default_project()
        self.view_state = MainWindowState()
        self.project_path: Path | None = None
        self.dirty = False
        self._editing_source_row: int | None = None
        self._source_added_at: dict[str, str] = {}
        self._active_page_container: str | None = None
        self._active_selection_container: str | None = None
        self.connector_registry = default_registry()
        self.secrets = RuntimeSecrets()
        self.thread_pool = QThreadPool.globalInstance()
        self.worker: Worker | None = None
        self.page_lookup_worker: Worker | None = None
        self.token: CancellationToken | None = None
        self.started_at = 0.0
        self.operation_controller = WorkerOperationController(self, self.thread_pool)
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("MainWindow requires an active QApplication")
        self.i18n = language_manager or LanguageManager(app, create_settings())
        if language_manager is None:
            self.i18n.set_language(self.i18n.preferred_language or "pt-BR", persist=False)
        self.i18n.language_changed.connect(self._language_changed)
        self.ui_settings = self.i18n.settings
        self._loading_source_form = False
        self._page_render_limits: dict[tuple[str, str], int] = {}
        self._selection_render_limits: dict[tuple[str, str], int] = {}
        self._selection_changing = False
        self._selection_flush_queued = False
        self._space_card_animations: list[QPropertyAnimation] = []
        self.log_path = default_log_path()
        self.technical_logger = configure_logging(self.log_path)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.pages: dict[str, QWidget] = {}
        self.setWindowTitle(APP_TITLE)
        self.logo_path = Path(__file__).with_name("assets") / "d20.svg"
        self.setWindowIcon(QIcon(str(self.logo_path)))
        self.resize(1440, 900)
        self.setMinimumSize(1050, 700)
        self._build()
        self._load_project_ui()
        self._update_load_context()
        self._show_page("dashboard")
        self.retranslate_ui()

    def _language_changed(self, _language: str) -> None:
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        """Refresh the visible UI while keeping internal combo data stable."""
        language_combo = getattr(self, "language_combo", None)
        excluded = (language_combo,) if language_combo is not None else ()
        retranslate_widget_tree(self, exclude=excluded)
        if language_combo is not None:
            selected = self.i18n.language
            index = language_combo.findData(selected)
            if index >= 0 and language_combo.currentIndex() != index:
                blocker = QSignalBlocker(language_combo)
                language_combo.setCurrentIndex(index)
                del blocker

    def _change_language(self, language: str) -> None:
        self.i18n.set_language(language)

    @property
    def trees(self) -> dict[str, dict[str, Any]]:
        return self.view_state.trees

    @property
    def selection_store(self) -> SelectionStore:
        return self.view_state.selection_store

    @selection_store.setter
    def selection_store(self, value: SelectionStore) -> None:
        self.view_state.selection_store = value

    @property
    def connection_states(self) -> dict[str, str]:
        return self.view_state.connection_states

    @property
    def last_result(self) -> dict[str, Any]:
        return self.view_state.last_result

    @last_result.setter
    def last_result(self, value: dict[str, Any]) -> None:
        self.view_state.last_result = value

    @property
    def last_consolidation_preview(self) -> list[dict[str, Any]]:
        return self.view_state.last_consolidation_preview

    @last_consolidation_preview.setter
    def last_consolidation_preview(self, value: list[dict[str, Any]]) -> None:
        self.view_state.last_consolidation_preview = value

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(235)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 20, 14, 16)
        brand_row = QHBoxLayout()
        brand_icon = QLabel()
        brand_icon.setPixmap(
            QPixmap(str(self.logo_path)).scaled(
                36,
                36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        brand_icon.setAccessibleName("Logotipo em forma de dado de vinte faces")
        brand = QLabel("ALQuimista")
        brand.setObjectName("brand")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand, 1)
        side.addLayout(brand_row)
        tagline = QLabel("Transforme conhecimento")
        tagline.setObjectName("subtitle")
        side.addWidget(tagline)
        side.addSpacing(18)
        for key, label in NAVIGATION:
            nav = QPushButton(label)
            nav.setObjectName("navButton")
            nav.setIcon(AlchemistIconAtlas.icon(NAV_ICON_INDEX.get(key, 15), 22))
            nav.setIconSize(QSize(22, 22))
            nav.setCheckable(True)
            nav.clicked.connect(lambda _checked=False, name=key: self._show_page(name))
            self.nav_buttons[key] = nav
            side.addWidget(nav)
        side.addStretch()
        self.project_badge = QLabel("● Projeto não salvo")
        self.project_badge.setObjectName("subtitle")
        side.addWidget(self.project_badge)
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        top = QFrame()
        top.setObjectName("card")
        top.setStyleSheet("border-radius: 0; border-top: 0; border-left: 0; border-right: 0;")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(22, 10, 22, 10)
        self.top_project = QLabel(self.project.project_name)
        self.top_project.setStyleSheet("font-weight: 700;")
        top_layout.addWidget(self.top_project)
        top_layout.addStretch()
        settings_button = button(
            "Configurações", lambda: self._show_page("settings")
        )
        settings_button.setIcon(AlchemistIconAtlas.icon(9, 22))
        settings_button.setIconSize(QSize(22, 22))
        top_layout.addWidget(settings_button)
        save_button = button("Salvar", self.save_project, primary=True)
        save_button.setIcon(AlchemistIconAtlas.icon(15, 22))
        save_button.setIconSize(QSize(22, 22))
        top_layout.addWidget(save_button)
        content.addWidget(top)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        outer.addLayout(content, 1)

        builders = {
            "dashboard": self._dashboard_page,
            "sources": self._sources_page,
            "connection": self._connection_page,
            "selection": self._selection_page,
            "markdown": self._markdown_page,
            "consolidation": self._consolidation_page,
            "extraction": self._review_page,
            "results": self._results_page,
            "settings": self._settings_page,
        }
        for key in (item[0] for item in NAVIGATION):
            if key not in builders:
                continue
            page = builders[key]()
            self.pages[key] = page
            self.stack.addWidget(page)
        settings_page = builders["settings"]()
        self.pages["settings"] = settings_page
        self.stack.addWidget(settings_page)
        # Mantém a tela de seleção materializada para compartilhar o mesmo snapshot.
        # Selection is built once above; all handlers point to the same page.
        self.pages["review"] = self.pages["extraction"]
        self.pages["pages"] = self._pages_page()
        self.stack.addWidget(self.pages["pages"])
        self.pages["output"] = self.pages["extraction"]

    def _dashboard_page(self) -> QWidget:
        return build_dashboard_page(self)

    def _source_card_clicked(self, source_type: str) -> None:
        """Open the source editor and preselect the platform represented by the card."""
        self._show_page("sources")
        platform_index = self.src_platform.findData(source_type)
        if platform_index >= 0:
            self.src_platform.setCurrentIndex(platform_index)

    def _metric(self, value: str, label: str, emoji: str) -> QFrame:
        frame, layout = card()
        row = QHBoxLayout()
        icon = QLabel(emoji)
        icon.setStyleSheet("font-size: 24pt;")
        row.addWidget(icon)
        text = QVBoxLayout()
        number = QLabel(value)
        number.setObjectName("metric")
        number.setProperty("metric_name", label)
        text.addWidget(number)
        muted = QLabel(label)
        muted.setObjectName("subtitle")
        text.addWidget(muted)
        row.addLayout(text)
        layout.addLayout(row)
        return frame

    def _configure_data_tree(
        self, tree: QTreeWidget, widths: list[int], settings_key: str
    ) -> None:
        """Apply one predictable, spreadsheet-like header behavior."""
        tree.setSortingEnabled(False)
        tree.setProperty("_alquimista_sort_column", -1)
        tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = tree.header()
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(70)
        header.setHighlightSections(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(True)
        for column, width in enumerate(widths):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            tree.setColumnWidth(column, width)
        # The provider order is the canonical hierarchy order. Sorting is
        # handled explicitly by _sort_tree_by_column; leaving Qt's automatic
        # sorting enabled would make one header click run two sort handlers
        # and prevent reliable asc/desc toggling.
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setAccessibleName("Tabela com colunas ordenáveis e reorganizáveis")
        saved = self.ui_settings.value(f"tables/{settings_key}")
        if saved:
            header.restoreState(saved)
        header.sectionMoved.connect(
            lambda *_args: self.ui_settings.setValue(
                f"tables/{settings_key}", header.saveState()
            )
        )
        def resized(logical: int, _old: int, new: int) -> None:
            bounded = max(70, min(720, new))
            if bounded != new:
                header.resizeSection(logical, bounded)
            self.ui_settings.setValue(f"tables/{settings_key}", header.saveState())

        header.sectionResized.connect(resized)
        # sectionClicked dispara a ordenacao explicita (sem reordenar a
        # arvore implicitamente ao carregar) e alterna asc/desc a cada clique.
        header.sectionClicked.connect(
            lambda column: self._sort_tree_by_column(tree, column)
        )

    def _sort_tree_by_column(self, tree: QTreeWidget, column: int) -> None:
        """Sort ``tree`` by ``column``, toggling ascending/descending.

        Clicking the same column repeatedly flips the order; clicking a
        different column starts ascending. The sort indicator is updated so
        the header reflects the active sort, but the provider order is kept
        on a freshly loaded tree (indicator cleared via -1).
        """
        header = tree.header()
        current_section = tree.property("_alquimista_sort_column")
        current_order = tree.property("_alquimista_sort_order")
        if current_section == column:
            next_order = (
                Qt.SortOrder.DescendingOrder
                if current_order == Qt.SortOrder.AscendingOrder.value
                else Qt.SortOrder.AscendingOrder
            )
        else:
            next_order = Qt.SortOrder.AscendingOrder
        tree.setProperty("_alquimista_sort_column", column)
        tree.setProperty("_alquimista_sort_order", next_order.value)
        header.setSortIndicator(column, next_order)
        tree.sortItems(column, next_order)
        QTimer.singleShot(
            0,
            lambda: self._finalize_tree_sort(tree, column, next_order),
        )

    def _finalize_tree_sort(
        self, tree: QTreeWidget, column: int, order: Qt.SortOrder
    ) -> None:
        """Keep the manual sort indicator after Qt finishes the click event."""
        if (
            tree.property("_alquimista_sort_column") != column
            or tree.property("_alquimista_sort_order") != order.value
        ):
            return
        tree.header().setSortIndicator(column, order)
        tree.sortItems(column, order)

    def _restore_table_columns(
        self, tree: QTreeWidget, widths: list[int], settings_key: str
    ) -> None:
        header = tree.header()
        for logical in range(header.count()):
            visual = header.visualIndex(logical)
            if visual != logical:
                header.moveSection(visual, logical)
            tree.setColumnWidth(logical, widths[logical])
        self.ui_settings.remove(f"tables/{settings_key}")
        self.statusBar().showMessage(
            translate_text("Organização padrão das colunas restaurada."), 3500
        )

    def _move_page_column(self, direction: int) -> None:
        logical = self.page_column_choice.currentData()
        if logical is None:
            return
        header = self.page_tree.header()
        current = header.visualIndex(int(logical))
        target = max(0, min(header.count() - 1, current + direction))
        if target != current:
            header.moveSection(current, target)
            self.statusBar().showMessage(
                f"Coluna {self.page_column_choice.currentText()} movida para a posição {target + 1}.",
                3500,
            )

    def _send_page_column(self, to_end: bool) -> None:
        logical = self.page_column_choice.currentData()
        if logical is None:
            return
        header = self.page_tree.header()
        current = header.visualIndex(int(logical))
        target = header.count() - 1 if to_end else 0
        if target != current:
            header.moveSection(current, target)
            destination = "fim" if to_end else "início"
            self.statusBar().showMessage(
                f"Coluna {self.page_column_choice.currentText()} enviada para o {destination}.",
                3500,
            )

    def _sources_page(self) -> QWidget:
        return build_sources_page(self)

    def _connection_page(self) -> QWidget:
        return build_connection_page(self)

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
        self.tree_load_button = button("🌳 Carregar espaços", self.load_tree, primary=True)
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
        self.page_space_search.setPlaceholderText("🔎 Pesquisar por nome do espaço…")
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
        self.page_back_button = button("← Voltar aos espaços", self._page_go_back)
        detail_tools.addWidget(self.page_back_button)
        self.page_space_title = QLabel("Espaço selecionado")
        self.page_space_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        detail_tools.addWidget(self.page_space_title)
        detail_tools.addStretch()
        detail_layout.addLayout(detail_tools)

        page_headers = ["Título", "Tipo", "Page ID", "Módulo", "Caminho", "Versão", "Atualização"]
        # Kept hidden for compatibility with existing column-management
        # methods. Users now organize the visible header directly by dragging.
        self.page_column_choice = QComboBox()
        for logical, title in enumerate(page_headers):
            self.page_column_choice.addItem(title, logical)
        self.page_column_choice.setAccessibleName("Coluna que será movimentada")
        self.page_column_choice.setVisible(False)

        summary, summary_layout = card()
        summary.setObjectName("pageSummaryCard")
        summary_row = QHBoxLayout()
        self.page_space_stat = self._page_stat("🌳", "Espaço selecionado", "—")
        self.page_count_stat = self._page_stat("📄", "Páginas", "0")
        self.page_sync_stat = self._page_stat("⟳", "Última sincronização", "Ainda não")
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
        self.page_tree.setItemDelegateForColumn(0, VisibilityBadgeDelegate(self.page_tree))
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
            self._set_page_stat(self.page_sync_stat, "Ainda não")
            return
        root = (data or {}).get("root", {}) or {}
        space_name = source.space_name or source.space_key or str(root.get("title") or "—")
        count = str(len((data or {}).get("pages", []) or []))
        loaded_at = str((data or {}).get("loaded_at") or "")
        if loaded_at:
            try:
                sync_label = datetime.fromisoformat(
                    loaded_at.replace("Z", "+00:00")
                ).astimezone().strftime("%d/%m/%Y %H:%M")
            except ValueError:
                sync_label = loaded_at
        else:
            sync_label = "Ainda não"
        self._set_page_stat(self.page_space_stat, space_name)
        self._set_page_stat(self.page_count_stat, count)
        self._set_page_stat(self.page_sync_stat, sync_label)

    def _selection_page(self) -> QWidget:
        return build_selection_page(self)

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
    def _container_requires_full_load(data: dict[str, Any], container_id: str) -> bool:
        """Return whether the current snapshot contains roots only."""
        state = (data.get("lazy_discovery") or {}).get(str(container_id), {}) or {}
        return bool(state.get("enabled") and not state.get("full_loaded"))


    def _selection_containers(self, source: SourceConfig) -> list[dict[str, Any]]:
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
        original_order = {str(container["id"]): index for index, container in enumerate(result)}
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
        source = self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        data = self.trees.get(source.id) if source else None
        containers = self._tree_containers(source, data or {}) if source else []
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
            loaded = bool(container.get("loaded")) or container_id in (data or {}).get(
                "pages_by_container", {}
            )
            count = len(self._tree_pages(data or {}, container_id)) if loaded else int(
                container.get("page_count", 0) or 0
            )
            subtitle = (
                f"{count} páginas carregadas"
                if loaded
                else "Clique para carregar as páginas"
            )
            visibility, visibility_kind = self._container_visibility(source, data or {}, container)
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
        query = (text if text is not None else self.page_space_search.text()).strip().casefold()
        self._reflow_space_cards(self.page_cards_layout, self._page_container_cards, query)

    def _open_page_container(self, container_id: str) -> None:
        source = self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        data = self.trees.get(source.id) if source else None
        if not source or data is None:
            return
        if self.worker is not None:
            self.tree_load_status.setText(translate_text("Aguarde a operação atual terminar…"))
            return
        self._active_page_container = str(container_id)
        container = next(
            (item for item in self._tree_containers(source, data) if item["id"] == str(container_id)),
            {"id": container_id, "name": container_id},
        )
        self.page_space_title.setText(f"🗂  {container['name']}")
        if hasattr(self, "pages_stack"): self.pages_stack.setCurrentIndex(1)
        self._update_load_context()
        # A tela de espaços usa carregamento leve; o detalhe materializa o
        # inventário completo quando o snapshot atual contém apenas raízes.
        if self._container_loaded(source, data, str(container_id)) and not self._container_requires_full_load(
            data, str(container_id)
        ):
            self._populate_page_tree(source, data, container_id=str(container_id))
            self._refresh_page_summary(
                source, {**data, "pages": self._tree_pages(data, str(container_id))}
            )
            return
        self._load_container_for_source(
            source, str(container_id), target="pages", load_all=True
        )

    def _page_go_back(self) -> None:
        self._active_page_container = None
        if hasattr(self, "pages_stack"): self.pages_stack.setCurrentIndex(0)
        self._update_load_context()
        self._refresh_pages_home()

    def _page_render_key(self, source: SourceConfig, container_id: str) -> tuple[str, str]:
        return source.id, str(container_id)

    def _load_more_page_rows(self) -> None:
        source = self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        if not source or not self._active_page_container:
            return
        key = self._page_render_key(source, self._active_page_container)
        self._page_render_limits[key] = self._page_render_limits.get(key, 800) + 800
        data = self.trees.get(source.id)
        if data:
            self._populate_page_tree(
                source, data, container_id=self._active_page_container
            )


    def _reflow_space_cards(
        self,
        layout: QGridLayout,
        cards: dict[str, SourceCard],
        query: str,
    ) -> None:
        """Repack matching cards into two rows inside the visible viewport."""
        if not cards:
            return
        for animation in self._space_card_animations:
            animation.stop()
        self._space_card_animations.clear()
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)
        matches = [
            card
            for card in cards.values()
            if not query
            or query in str(card.property("container_name") or "").casefold()
        ]
        for card_widget in cards.values():
            card_widget.setVisible(False)
        for index, card_widget in enumerate(matches):
            layout.addWidget(card_widget, index % 2, index // 2)
            card_widget.setVisible(True)
            card_widget.setEnabled(True)
        layout.activate()
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        scroll = None
        if layout is getattr(self, "page_cards_layout", None):
            scroll = self.page_cards_scroll
        elif layout is getattr(self, "selection_cards_layout", None):
            scroll = self.selection_cards_scroll
        if matches and scroll is not None:
            scroll.horizontalScrollBar().setValue(0)
            scroll.verticalScrollBar().setValue(0)
            scroll.ensureWidgetVisible(matches[0], 8, 8)


    def _markdown_page(self) -> QWidget:
        return build_markdown_page(self)
    def _set_markdown_sections(self, expanded: bool) -> None:
        for current in getattr(self, "markdown_sections", []):
            current.set_expanded(expanded)

    def _extraction_page(self) -> QWidget:
        return build_extraction_page(self)
    def _consolidation_page_legacy(self) -> QWidget:
        page, layout = page_header(
            "Pacotes para NotebookLM e RAG",
            "Visualize a distribuição antes de gerar os arquivos.",
            "📦",
        )
        controls, controls_layout = card()
        form = QFormLayout()
        self.con_group = QComboBox()
        for label, value in [
            ("Tudo em uma sequência", "single"),
            ("Separar por fonte", "source"),
            ("Separar por espaço", "space"),
            ("Separar por módulo — profundidade escolhida", "module"),
            ("Separar por módulo e submódulo", "module_submodule"),
            ("Separar por fonte e módulo (recomendado)", "source_module"),
            ("Separar por fonte, módulo e submódulo", "source_module_submodule"),
            ("Grupos definidos manualmente", "manual"),
        ]:
            self.con_group.addItem(label, value)
        self.con_pages = QSpinBox()
        self.con_pages.setRange(1, 10000)
        self.con_chars = QSpinBox()
        self.con_chars.setRange(1000, 100_000_000)
        self.con_depth = QSpinBox()
        self.con_depth.setRange(1, 10)
        self.con_depth.setToolTip(
            translate_text(
                "1 = primeiro módulo abaixo da raiz; 2 = módulo e submódulo; e assim por diante."
            )
        )
        self.con_depth_choice = QComboBox()
        for level in range(1, 11):
            detail = "módulo principal" if level == 1 else f"módulo + {level - 1} subnível(is)"
            self.con_depth_choice.addItem(f"Nível {level} — {detail}", level)
        self.con_depth_choice.currentIndexChanged.connect(self._depth_choice_changed)
        self.con_depth_example = QLabel()
        self.con_depth_example.setObjectName("subtitle")
        self.con_depth_example.setWordWrap(True)
        self.con_prefix = QLineEdit()
        self.con_hierarchy = QCheckBox("Repetir a árvore no arquivo consolidado")
        self.con_hierarchy.setToolTip(
            translate_text("Inclui os níveis do caminho como títulos antes de cada documento.")
        )
        form.addRow("Agrupamento", self.con_group)
        self.con_group_help = QLabel(
            "Define quais páginas ficam juntas. “Fonte e módulo” costuma produzir "
            "arquivos menores, organizados e fáceis de localizar."
        )
        self.con_group_help.setObjectName("subtitle")
        self.con_group_help.setWordWrap(True)
        form.addRow("", self.con_group_help)
        form.addRow("Máximo de páginas", self.con_pages)
        pages_help = QLabel(
            "Limite por arquivo. Exemplo: com 120 páginas e limite 50, serão criados "
            "aproximadamente 3 arquivos (50 + 50 + 20)."
        )
        pages_help.setObjectName("subtitle")
        pages_help.setWordWrap(True)
        form.addRow("", pages_help)
        form.addRow("Máximo de caracteres", self.con_chars)
        chars_help = QLabel(
            "Limita o texto total, incluindo espaços e formatação. Este limite funciona "
            "junto com o de páginas. Uma página nunca é cortada ao meio; se ela exceder "
            "sozinha o limite, será mantida inteira e marcada com aviso. Recomendado: 2.000.000."
        )
        chars_help.setObjectName("subtitle")
        chars_help.setWordWrap(True)
        form.addRow("", chars_help)
        form.addRow("Profundidade dos módulos", self.con_depth)
        depth_help = QLabel(
            "Nível 1 agrupa pelo primeiro módulo, como “Acesso ao Sistema”. "
            "Nível 2 separa também o próximo nível, como “Barra de Cabeçalho” e "
            "Use a profundidade para escolher quantos níveis da hierarquia entram no agrupamento."
        )
        depth_help.setObjectName("subtitle")
        depth_help.setWordWrap(True)
        form.addRow("", depth_help)
        form.addRow("Prefixo", self.con_prefix)
        form.addRow("Estrutura", self.con_hierarchy)
        self.con_filename_preview = QLabel("Exemplo de arquivo: pacote-01.md")
        self.con_filename_preview.setObjectName("subtitle")
        form.addRow("", self.con_filename_preview)
        controls_layout.addLayout(form)
        self.con_summary = QLabel()
        self.con_summary.setWordWrap(True)
        self.con_summary.setStyleSheet("font-weight: 600;")
        controls_layout.addWidget(self.con_summary)
        actions = QHBoxLayout()
        actions.addWidget(button("👁 Prévia da distribuição", self.preview_consolidation))
        actions.addWidget(button("📦 Gerar pacotes", self.run_consolidation, primary=True))
        controls_layout.addLayout(actions)
        layout.addWidget(controls)
        self.package_table = QTableWidget(0, 5)
        self.package_table.setHorizontalHeaderLabels(
            ["Grupo", "Parte", "Páginas", "Caracteres", "Observação"]
        )
        self.package_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.package_table, 1)
        self.con_group.currentIndexChanged.connect(self._update_consolidation_summary)
        self.con_pages.valueChanged.connect(self._update_consolidation_summary)
        self.con_chars.valueChanged.connect(self._update_consolidation_summary)
        self.con_depth.valueChanged.connect(self._update_consolidation_summary)
        self.con_hierarchy.toggled.connect(self._update_consolidation_summary)
        self.con_prefix.textChanged.connect(self._update_consolidation_summary)
        self.con_group.currentIndexChanged.connect(self._mark_consolidation_preview_stale)
        self.con_pages.valueChanged.connect(self._mark_consolidation_preview_stale)
        self.con_chars.valueChanged.connect(self._mark_consolidation_preview_stale)
        self.con_depth.valueChanged.connect(self._mark_consolidation_preview_stale)
        self.con_hierarchy.toggled.connect(self._mark_consolidation_preview_stale)
        self.con_prefix.textChanged.connect(self._mark_consolidation_preview_stale)
        return page

    def _consolidation_page(self) -> QWidget:
        return build_consolidation_page(self)
    def _results_page(self) -> QWidget:
        return build_results_page(self)
    def _output_page(self) -> QWidget:
        page, layout = page_header(
            "Pasta de saída",
            "Escolha a pasta principal. O ALQuimista separa arquivos soltos e pacotes consolidados em subpastas.",
            "",
        )
        content, content_layout = card()
        title = QLabel("Onde deseja salvar os arquivos?")
        title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        content_layout.addWidget(title)
        self.output_dir = QLineEdit()
        self.output_dir.setAccessibleName("Pasta onde os arquivos serão salvos")
        self.output_dir.setPlaceholderText("Escolha uma pasta no computador")
        self.output_dir.textChanged.connect(self._update_output_preview)
        self.output_controls = ResponsiveOutputControls(
            self.output_dir,
            [
                button("Escolher pasta", self.choose_output, primary=True),
                button("Abrir pasta", self.open_output),
            ],
        )
        content_layout.addWidget(self.output_controls)
        self.output_path_status = QLabel()
        self.output_path_status.setWordWrap(True)
        content_layout.addWidget(self.output_path_status)
        self.output_subfolder = QCheckBox("Criar uma subpasta para esta execução")
        self.output_subfolder.setChecked(True)
        self.output_subfolder.toggled.connect(self._update_output_preview)
        content_layout.addWidget(self.output_subfolder)
        self.output_structure = QLabel()
        self.output_structure.setObjectName("subtitle")
        self.output_structure.setWordWrap(True)
        content_layout.addWidget(self.output_structure)
        layout.addWidget(content)
        layout.addStretch()
        self._update_output_preview()
        return page

    def _review_page_legacy(self) -> QWidget:
        page, layout = page_header(
            "Revisão",
            "Confira as escolhas antes de iniciar. Você pode editar qualquer seção.",
            "",
        )
        summary, summary_layout = card()
        self.review_summary = QLabel()
        self.review_summary.setWordWrap(True)
        self.review_summary.setMinimumHeight(300)
        self.review_summary.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self.review_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        summary_layout.addWidget(self.review_summary)
        edit_grid = QGridLayout()
        for index, (label, target) in enumerate(
            [
                ("Editar fonte", "sources"),
                ("Editar conexão", "connection"),
                ("Editar seleção", "selection"),
                ("Editar formato", "markdown"),
                ("Editar consolidação", "consolidation"),
                ("Editar pasta", "output"),
            ]
        ):
            edit_grid.addWidget(
                button(label, lambda _checked=False, key=target: self._show_page(key)),
                index // 3,
                index % 3,
            )
        summary_layout.addLayout(edit_grid)
        layout.addWidget(summary)
        action_row = QHBoxLayout()
        action_row.addStretch()
        action_row.addWidget(
            button("Executar operação escolhida", self.execute_selected_operation, primary=True)
        )
        layout.addLayout(action_row)
        layout.addStretch()
        return page

    def _review_page(self) -> QWidget:
        return build_review_page(self)
    def _update_execution_mode_help(self, *_args: Any) -> None:
        if not hasattr(self, "execution_mode_help"):
            return
        self.execution_mode_help.setText(
            {
                "complete": translate_text(
                    "Executa a extração das páginas selecionadas e depois cria os pacotes consolidados."
                ),
                "extract": translate_text(
                    "Busca somente as páginas selecionadas e atualiza os arquivos Markdown individuais."
                ),
                "consolidate": translate_text(
                    "Usa os arquivos e o manifesto já extraídos para criar os pacotes consolidados."
                ),
            }.get(str(self.execution_mode.currentData()), "")
        )

    def _settings_page(self) -> QWidget:
        page, layout = page_header(
            "Configurações",
            "Ajuste aparência, rede e comportamento seguro.",
            "🔧",
        )
        settings_help = QLabel(
            "As opções comuns ficam primeiro. Rede é uma área avançada; mantenha os "
            "valores recomendados se não souber o que alterar. Mudanças ficam pendentes "
            "até você salvar o projeto."
        )
        settings_help.setWordWrap(True)
        settings_help.setObjectName("subtitle")
        layout.addWidget(settings_help)
        project_card, project_layout = card()
        form = QFormLayout()
        self.project_name = QLineEdit()
        form.addRow("Nome do projeto", self.project_name)
        output_help = QLabel(
            "A pasta de saída é configurada na etapa 08. As alterações ficam pendentes "
            "até o projeto ser salvo."
        )
        output_help.setObjectName("subtitle")
        output_help.setWordWrap(True)
        form.addRow("", output_help)
        project_layout.addLayout(form)
        project_actions = QHBoxLayout()
        project_actions.addWidget(button("➕ Novo projeto", self.new_project))
        project_actions.addWidget(button("📂 Abrir projeto", self.open_project))
        project_actions.addWidget(button("💾 Salvar como", self.save_project_as, primary=True))
        project_layout.addLayout(project_actions)
        layout.addWidget(project_card)
        appearance, appearance_layout = card()
        appearance_layout.addWidget(QLabel("🎨 Aparência"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["system", "light", "dark"])
        self.theme_combo.currentTextChanged.connect(
            lambda value: apply_theme(QApplication.instance(), value)
        )
        appearance_layout.addWidget(self.theme_combo)
        language_label = QLabel("🌐 Idioma da interface")
        appearance_layout.addWidget(language_label)
        self.language_combo = QComboBox()
        for code, label in LANGUAGE_NAMES.items():
            self.language_combo.addItem(label, code)
        self.language_combo.setCurrentIndex(
            max(0, self.language_combo.findData(self.i18n.language))
        )
        self.language_combo.currentIndexChanged.connect(
            lambda _index: self._change_language(str(self.language_combo.currentData()))
        )
        appearance_layout.addWidget(self.language_combo)
        layout.addWidget(appearance)
        network, network_layout = card()
        network_layout.addWidget(QLabel("⚙ Rede (avançado)"))
        form = QFormLayout()
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 600)
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 10)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 60000)
        form.addRow("Timeout de leitura (s)", self.timeout_spin)
        form.addRow("Tentativas", self.retries_spin)
        form.addRow("Intervalo entre páginas (ms)", self.delay_spin)
        network_layout.addLayout(form)
        network_layout.addWidget(
            button("↺ Restaurar valores recomendados", self._restore_network_defaults)
        )
        layout.addWidget(network)
        layout.addStretch()
        return page



    def _set_metric(self, frame: QFrame, value: str) -> None:
        for label in frame.findChildren(QLabel):
            if label.objectName() == "metric":
                label.setText(value)
                return

    def mark_dirty(self) -> None:
        self.dirty = True
        self.project_badge.setText(translate_text("● Alterações não salvas"))

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        return (
            QMessageBox.question(
                self,
                translate_text("Alterações não salvas"),
                translate_text("Descartar as alterações que ainda não foram salvas?"),
            )
            == QMessageBox.StandardButton.Yes
        )

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = default_project()
        self.selection_store = SelectionStore.from_selections(self.project.selections)
        self.project_path = None
        self.trees.clear()
        self.secrets.clear()
        self.dirty = False
        self._load_project_ui()
        self._show_page("dashboard")

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        selected, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Abrir projeto"),
            "",
            translate_text("Projeto ALQuimista (*.json)"),
        )
        if not selected:
            return
        try:
            candidate_path = Path(selected).resolve()
            candidate_project = load_project_file(candidate_path)
            self.project_path = candidate_path
            self.project = candidate_project
            self.selection_store = SelectionStore.from_selections(self.project.selections)
            self.trees.clear()
            self.secrets.clear()
            self.dirty = False
            self._load_project_ui()
            self._append_log(f"Projeto aberto: {self.project_path}")
        except Exception as exc:
            QMessageBox.critical(self, translate_text("Projeto inválido"), str(exc))

    def save_project(self) -> bool:
        if self.project_path is None:
            self.save_project_as()
            return self.project_path is not None and not self.dirty
        try:
            self._sync_project_ui()
            save_project_file(self.project_path, self.project)
            self.dirty = False
            self.project_badge.setText(
                translate_text("● Salvo em {path}").format(path=self.project_path.name)
            )
            self.top_project.setText(self.project.project_name)
            return True
        except Exception as exc:
            QMessageBox.critical(self, translate_text("Falha ao salvar"), str(exc))
            return False

    def save_project_as(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Salvar projeto"),
            "projeto_alquimista.json",
            translate_text("Projeto ALQuimista (*.json)"),
        )
        if selected:
            previous_path = self.project_path
            self.project_path = Path(selected).resolve()
            if not self.save_project():
                self.project_path = previous_path

    def _project_dir(self) -> Path:
        return resolve_project_dir(self.project_path)

    def _load_project_ui(self) -> None:
        self.selection_store = SelectionStore.from_selections(self.project.selections)
        self.top_project.setText(self.project.project_name)
        self.project_badge.setText(
            translate_text("● Salvo em {path}").format(path=self.project_path.name)
            if self.project_path
            else translate_text("● Projeto não salvo")
        )
        self.project_name.setText(self.project.project_name)
        self.output_dir.setText(self.project.output_dir)
        self.timeout_spin.setValue(self.project.extraction.timeout_seconds)
        self.retries_spin.setValue(self.project.extraction.retry_count)
        self.delay_spin.setValue(self.project.extraction.request_delay_ms)
        if hasattr(self, "sources_list"):
            self._refresh_source_widgets()
        if hasattr(self, "md_controls"):
            self._load_markdown_controls()
        self._sync_consolidation_ui()
        self._refresh_dashboard()
        self._update_extraction_summary()
        # Loading values may emit Qt signals; they do not represent user edits.
        self.dirty = False
        self.project_badge.setText(
            translate_text("● Salvo em {path}").format(path=self.project_path.name)
            if self.project_path
            else translate_text("● Projeto não salvo")
        )

    def _sync_project_ui(self, *, strict: bool = True) -> bool:
        source_valid = True
        if hasattr(self, "sources_list"):
            source_valid = self.apply_source(silent=True)
            if strict and not source_valid:
                raise ValueError(
                    "A fonte atual contém dados inválidos. Corrija os campos antes de continuar."
                )
        self.project.project_name = self.project_name.text().strip() or "Projeto ALQuimista"
        self.project.output_dir = self.output_dir.text().strip() or "ALQuimista_Base"
        self.project.extraction.timeout_seconds = self.timeout_spin.value()
        self.project.extraction.retry_count = self.retries_spin.value()
        self.project.extraction.request_delay_ms = self.delay_spin.value()
        if hasattr(self, "md_controls"):
            self._sync_markdown_controls()
        self._sync_consolidation_controls()
        return source_valid

    def _tree_source_changed(self) -> None:
        source = self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        if source and source.id in self.trees:
            self._active_page_container = None
            if hasattr(self, "pages_stack"): self.pages_stack.setCurrentIndex(0)
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
        """Keep the load action aligned with the current spaces/pages view."""
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
        page_text = translate_text("Carregar páginas" if page_detail else "Carregar espaços")
        selection_text = (
            translate_text("Carregar páginas" if selection_detail else "Carregar espaços")
        )
        if hasattr(self, "tree_load_button"):
            self.tree_load_button.setText(page_text)
            self.tree_load_button.setIcon(AlchemistIconAtlas.icon(3, 20))
            self.tree_load_button.setIconSize(QSize(20, 20))
        if hasattr(self, "selection_load_button"):
            self.selection_load_button.setText(selection_text)
            self.selection_load_button.setIcon(AlchemistIconAtlas.icon(3, 20))
            self.selection_load_button.setIconSize(QSize(20, 20))

    def _set_tree_loading(self, loading: bool, message: str | None = None) -> None:
        self._tree_loading = loading
        buttons = [
            (
                getattr(self, "tree_load_button", None),
                translate_text(
                    "Carregar páginas"
                    if self._active_page_container
                    else "Carregar espaços"
                ),
            ),
            (
                getattr(self, "selection_load_button", None),
                translate_text(
                    "Carregar páginas"
                    if self._active_selection_container
                    else "Carregar espaços"
                ),
            ),
        ]
        for current, idle_text in buttons:
            if current is None:
                continue
            current.setEnabled(not loading)
            if loading:
                current.setText(translate_text("⏳ Carregando…"))
                current.setIcon(AlchemistIconAtlas.icon(7, 20))
            else:
                current.setText(idle_text)
                current.setIcon(AlchemistIconAtlas.icon(3, 20))
            current.setIconSize(QSize(20, 20))
        for current in (
            getattr(self, "tree_cancel_button", None),
            getattr(self, "selection_cancel_button", None),
        ):
            if current is not None:
                current.setEnabled(loading)
        if hasattr(self, "tree_load_status"):
            self.tree_load_status.setText(
                translate_text(message)
                if message
                else (
                    translate_text("Carregando espaços e páginas…")
                    if loading
                    else translate_text("Pronto para carregar espaços.")
                )
            )
        if hasattr(self, "tree_load_progress"):
            self.tree_load_progress.setVisible(loading)
            if loading:
                self.tree_load_progress.setRange(0, 0)
        if loading:
            self.statusBar().showMessage(translate_text("Carregando espaços e páginas…"))

    def _cancel_tree_operation(self) -> None:
        """Cancel a tree/space load immediately, without a confirmation dialog."""
        if not self._tree_loading or self.token is None:
            return
        self.token.cancel()
        message = translate_text("Cancelamento solicitado. Finalizando a requisição atual…")
        if hasattr(self, "tree_load_status"):
            self.tree_load_status.setText(message)
        self.statusBar().showMessage(message)

    def load_tree(self) -> None:
        if (
            getattr(self, "pages_stack", None)
            and self.pages_stack.currentIndex() == 1
            and self._active_page_container
        ):
            source = self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
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
        source = self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        if not source:
            return
        if self.worker is not None:
            if hasattr(self, "tree_load_status"):
                self.tree_load_status.setText(
                    translate_text("Já existe uma operação em andamento…")
                )
            return
        self._set_tree_loading(True)
        if source.source_type in {"confluence_rest", "gitbook_api", "zendesk_guide"}:
            self._load_tree_via_connector(source)
            return

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            progress(0, 1, "Descobrindo espaços")
            with ConfluenceClient(
                source,
                self.project.extraction,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            ) as client:
                raw_containers = client.list_spaces()
            containers = [
                {
                    "id": str(item.get("key") or item.get("id") or ""),
                    "key": str(item.get("key") or item.get("id") or ""),
                    "name": str(item.get("name") or item.get("key") or "Sem nome"),
                    "metadata": {},
                }
                for item in raw_containers
                if item.get("key") or item.get("id")
            ]
            if source.space_key:
                containers = [
                    item for item in containers if item["id"] == source.space_key
                ] or containers
            progress(1, 1, f"{len(containers)} espaços encontrados")
            return {
                "root": {"id": "__all_containers__", "title": "Contêineres"},
                "containers": containers,
                "pages": [],
                "pages_by_container": {},
                "loaded_at": now_iso(),
            }

        def done(data: dict[str, Any]) -> None:
            self.trees[source.id] = data
            self._active_page_container = None
            if hasattr(self, "pages_stack"): self.pages_stack.setCurrentIndex(0)
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False, f"{len(data['containers'])} espaços encontrados. Escolha um para carregar."
            )
            self.statusBar().showMessage(
                f"{len(data['containers'])} espaços encontrados. Escolha um para carregar.", 5000
            )

        self._start_worker(work, done)

    def _load_tree_via_connector(self, source: SourceConfig) -> None:
        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            progress(0, 1, "Descobrindo espaços")
            connector = self.connector_registry.create(
                source,
                options=self.project.extraction,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            )
            try:
                containers = connector.list_containers()
            finally:
                connector.close()
            if source.source_type == "confluence_rest" and source.space_key:
                filtered = [item for item in containers if item.id == source.space_key]
                if filtered:
                    containers = filtered
            progress(1, 1, f"{len(containers)} espaços encontrados")
            return {
                "root": {"id": "__all_containers__", "title": "Contêineres"},
                "containers": [
                    {
                        "id": str(container.id),
                        "key": str(container.key or container.id),
                        "name": str(container.name),
                        "description": str(container.description or ""),
                        "image_url": str((container.metadata or {}).get("icon_url", "")),
                        "metadata": dict(container.metadata or {}),
                    }
                    for container in containers
                ],
                "pages": [],
                "pages_by_container": {},
                "loaded_at": now_iso(),
            }

        def done(data: dict[str, Any]) -> None:
            self.trees[source.id] = data
            self._active_page_container = None
            if hasattr(self, "pages_stack"): self.pages_stack.setCurrentIndex(0)
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False,
                f"{len(data['containers'])} espaços encontrados. Escolha um para carregar.",
            )
            self.statusBar().showMessage(
                f"{len(data['containers'])} espaços encontrados. Escolha um para carregar.", 5000
            )

        self._start_worker(work, done)

    @staticmethod
    def _container_page_dict(container: dict[str, Any], item: Any) -> dict[str, Any]:
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
                "space": {"key": container.get("key") or container["id"], "name": container["name"]},
                "version": {
                    "number": metadata.get("confluence_version"),
                    "when": updated_at.isoformat() if updated_at else "",
                },
                "_container_id": str(container["id"]),
                "parent_id": getattr(item, "parent_id", None) or metadata.get("parent_id"),
                "has_children": bool(
                    getattr(item, "has_children", False) or metadata.get("has_children", False)
                ),
                "original_url": str(getattr(item, "original_url", "") or ""),
                "etag": getattr(item, "etag", None) or metadata.get("etag"),
                "visibility": metadata.get("visibility")
                or getattr(getattr(item, "visibility", None), "value", None),
                "access": metadata.get("access"),
                "permission": metadata.get("permission"),
                "public": metadata.get("public"),
                "private": metadata.get("private"),
                "provider_ordered": bool(metadata.get("provider_ordered", False)),
            }
        page = dict(item)
        page["_container_id"] = str(container["id"])
        page.setdefault("parent_id", page.get("parentId"))
        page.setdefault("has_children", bool(page.get("hasChildren", False)))
        page.setdefault(
            "space", {"key": container.get("key") or container["id"], "name": container["name"]}
        )
        return page

    def _load_all_containers(self) -> None:
        sender = self.sender()
        source = (
            self._selection_source()
            if sender is getattr(self, "selection_load_button", None)
            else self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
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
            self._set_tree_loading(False, "Todos os espaços já estão carregados.")
            return

        self._set_tree_loading(True, f"Carregando 0 de {len(containers)} espaços…")

        def work(token: CancellationToken, progress: Any, log: Any) -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            connector = None
            try:
                if source.source_type in {"confluence_rest", "gitbook_api", "zendesk_guide"}:
                    connector = self.connector_registry.create(
                        source,
                        options=self.project.extraction,
                        secret=self.secrets.get(source.id, ""),
                        token=token,
                        log=log,
                    )
                for index, container in enumerate(containers, 1):
                    token.check()
                    container_id = str(container["id"])
                    progress(index - 1, len(containers), f"Abrindo {container['name']}")
                    if connector is not None:
                        documents = connector.list_documents(container_id)
                        pages = [
                            self._container_page_dict(container, item)
                            for item in documents
                        ]
                    else:
                        configured = source.model_copy(
                            update={
                                "space_key": container_id,
                                "space_name": container["name"],
                                "root_mode": "space",
                                "root_value": "",
                            }
                        )
                        with ConfluenceClient(
                            configured,
                            self.project.extraction,
                            secret=self.secrets.get(source.id, ""),
                            token=token,
                            log=log,
                        ) as client:
                            pages = [
                                self._container_page_dict(container, item)
                                for item in client.list_pages()
                            ]
                    results.append({"container_id": container_id, "pages": pages})
                    progress(index, len(containers), f"{len(pages)} páginas em {container['name']}")
            finally:
                if connector is not None:
                    connector.close()
            return results

        def done(results: list[dict[str, Any]]) -> None:
            current = self.trees.setdefault(source.id, data)
            pages_by_container = current.setdefault("pages_by_container", {})
            for result in results:
                pages_by_container[str(result["container_id"])] = result["pages"]
            current["pages"] = self._tree_pages(current)
            current["loaded_at"] = now_iso()
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False,
                f"{len(results)} espaços carregados. Escolha um para visualizar.",
            )

        self._start_worker(work, done)

    def _load_container_for_source(
        self,
        source: SourceConfig,
        container_id: str,
        *,
        target: str,
        load_all: bool = False,
    ) -> None:
        data = self.trees.get(source.id)
        if data is None or self.worker is not None:
            return
        container = next(
            (item for item in self._tree_containers(source, data) if item["id"] == container_id),
            {"id": container_id, "key": container_id, "name": container_id},
        )
        self._set_tree_loading(True, f"Carregando páginas de {container['name']}…")

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            progress(0, 1, f"Abrindo {container['name']}")
            lazy_enabled = False
            from_cache = False
            fallback_reason = ""
            if source.source_type in {"confluence_rest", "gitbook_api", "zendesk_guide"}:
                connector = self.connector_registry.create(
                    source,
                    options=self.project.extraction,
                    secret=self.secrets.get(source.id, ""),
                    token=token,
                    log=log,
                )
                try:
                    page = None if load_all else self._lazy_discovery_page(
                        source,
                        connector,
                        container_id,
                        parent_id=None,
                        token=token,
                    )
                    if load_all or page is None:
                        fallback_reason = (
                            "Carregamento completo solicitado para este espaço."
                            if load_all
                            else "O conector não expõe a descoberta completa por raiz e filhos; usando compatibilidade "
                            "legada, que carrega o inventário completo deste espaço."
                        )
                        documents = connector.list_documents(container_id)
                    else:
                        lazy_enabled = True
                        documents = list(page.items)
                        from_cache = bool(page.from_cache)
                    pages = [self._container_page_dict(container, item) for item in documents]
                finally:
                    connector.close()
            else:
                configured = source.model_copy(
                    update={
                        "space_key": container_id,
                        "space_name": container["name"],
                        "root_mode": "space",
                        "root_value": "",
                    }
                )
                with ConfluenceClient(
                    configured,
                    self.project.extraction,
                    secret=self.secrets.get(source.id, ""),
                    token=token,
                    log=log,
                ) as client:
                    fallback_reason = (
                        "A fonte legada não expõe descoberta por hierarquia; usando compatibilidade "
                        "legada, que carrega o inventário completo deste espaço."
                    )
                    pages = [self._container_page_dict(container, item) for item in client.list_pages()]
            progress(1, 1, f"{len(pages)} páginas encontradas em {container['name']}")
            return {
                "container_id": container_id,
                "pages": pages,
                "target": target,
                "lazy_enabled": lazy_enabled,
                "full_loaded": bool(load_all or not lazy_enabled),
                "fallback_reason": fallback_reason,
                "from_cache": from_cache,
            }

        def done(result: dict[str, Any]) -> None:
            current = self.trees.setdefault(source.id, data)
            pages_by_container = current.setdefault("pages_by_container", {})
            pages_by_container[container_id] = result["pages"]
            current.setdefault("lazy_discovery", {})[container_id] = {
                "enabled": bool(result.get("lazy_enabled")),
                "full_loaded": bool(result.get("full_loaded")),
                "loaded_parents": [],
                "fallback_reason": str(result.get("fallback_reason", "")),
            }
            current["pages"] = self._tree_pages(current)
            current["loaded_at"] = now_iso()
            # Loading the inventory must not change the user's selection.
            if self._active_page_container == container_id:
                self._populate_page_tree(source, current, container_id=container_id)
            if self._active_selection_container == container_id:
                self._populate_selection_tree(source, current, container_id=container_id)
            self._refresh_pages_home()
            self._refresh_selection_home()
            self._set_tree_loading(
                False,
                (
                    translate_text(
                        "{count} páginas-raiz carregadas em {name}."
                    ).format(count=len(result["pages"]), name=container["name"])
                    if result.get("lazy_enabled") and not result.get("full_loaded")
                    else translate_text(
                        "{count} páginas carregadas em {name}."
                    ).format(count=len(result["pages"]), name=container["name"])
                ),
            )
            self.statusBar().showMessage(
                str(
                    result.get("fallback_reason")
                    or translate_text("{count} páginas carregadas em {name}.").format(
                        count=len(result["pages"]), name=container["name"]
                    )
                ),
                7000,
            )

            if result.get("from_cache"):
                self.statusBar().showMessage(
                    translate_text("Resultado reutilizado do cache local."), 7000
                )

        self._start_worker(work, done)

    def _page_visibility(self, source: SourceConfig, page: dict[str, Any]) -> tuple[str, str]:
        return visibility_for_page(source, page)

    @staticmethod
    def _explicit_visibility_kind(page: dict[str, Any]) -> str | None:
        return explicit_visibility_kind(page)

    def _container_visibility(
        self, source: SourceConfig, data: dict[str, Any], container: dict[str, Any]
    ) -> tuple[str, str]:
        return visibility_for_container(source, data, container)

    def _lazy_method(connector: Any, operation: str) -> Any:
        """Return an optional lazy-discovery method without weakening legacy connectors."""
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
    def _browser_cache_path() -> Path:
        """Return the local metadata-cache path without incorporating secrets."""
        return session_directory().parent / "browser_metadata.sqlite3"

    @staticmethod
    def _browser_cache_scope(source: SourceConfig) -> str:
        """Partition discovery snapshots by authentication mode only."""
        return {
            AuthMode.PUBLIC: "public",
            AuthMode.BASIC: "basic",
            AuthMode.BEARER: "bearer",
            AuthMode.BROWSER: "session",
        }.get(source.auth_mode, "public")

    @classmethod
    def _lazy_discovery_page(
        cls,
        source: SourceConfig,
        connector: Any,
        container_id: str,
        *,
        parent_id: str | None,
        token: CancellationToken,
    ) -> Any | None:
        """Load one lazy page through the durable metadata-only cache.

        The cache is created only after the connector advertises the requested
        lazy capability. Legacy ``list_documents`` callers therefore remain
        network-only and are never silently cached as if they were lazy.
        """
        adapter = ConnectorDiscoveryAdapter(connector)
        capability = "list_document_children" if parent_id else "list_root_documents"
        if capability not in adapter.capabilities or not hasattr(connector, "get_source"):
            return None
        cache = BrowserCache(cls._browser_cache_path())
        service = LazyDiscoveryService(
            source.id,
            adapter,
            cache=cache,
            cache_scope=cls._browser_cache_scope(source),
        )
        if parent_id:
            return service.list_document_children(
                container_id,
                parent_id,
                limit=800,
                token=token,
            )
        return service.list_root_documents(container_id, limit=800, token=token)

    @classmethod
    def _lazy_documents(
        cls,
        connector: Any,
        container_id: str,
        *,
        parent_id: str | None,
        token: CancellationToken,
    ) -> list[Any] | None:
        """Compatibility helper for existing callers and lightweight doubles."""
        method = cls._lazy_method(connector, "children" if parent_id else "root")
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
    def _lazy_state(data: dict[str, Any], container_id: str) -> dict[str, Any]:
        return tree_lazy_state(data, container_id)

    def _page_tree_item_expanded(self, item: QTreeWidgetItem) -> None:
        self._load_expanded_document(item, target="pages")


    def _load_expanded_document(self, item: QTreeWidgetItem, *, target: str) -> None:
        source_id = str(item.data(0, VisibilityBadgeDelegate.SOURCE_ROLE) or "")
        container_id = str(item.data(0, VisibilityBadgeDelegate.CONTAINER_ROLE) or "")
        document_id = str(item.data(0, VisibilityBadgeDelegate.DOCUMENT_ROLE) or "")
        if not source_id or not container_id or not document_id:
            return
        source = next((candidate for candidate in self.project.sources if candidate.id == source_id), None)
        data = self.trees.get(source_id)
        if source is None or data is None:
            return
        state = self._lazy_state(data, container_id)
        if not state.get("enabled") or document_id in state.get("loaded_parents", []):
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
        )

    def _load_document_children(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        container_id: str,
        parent_id: str,
        *,
        target: str,
    ) -> None:
        container = next(
            (item for item in self._tree_containers(source, data) if item["id"] == container_id),
            {"id": container_id, "key": container_id, "name": container_id},
        )
        self._set_tree_loading(True, f"Carregando filhos de {parent_id}…")

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            progress(0, 1, f"Abrindo {parent_id}")
            connector = self.connector_registry.create(
                source,
                options=self.project.extraction,
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
                )
                if page is None and not hasattr(connector, "get_source"):
                    documents = self._lazy_documents(
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
                pages = [self._container_page_dict(container, item) for item in documents]
            finally:
                connector.close()
            progress(1, 1, f"{len(pages)} filhos encontrados")
            return {
                "container_id": container_id,
                "parent_id": parent_id,
                "pages": pages,
                "target": target,
                "from_cache": from_cache,
            }

        def done(result: dict[str, Any]) -> None:
            current = self.trees.setdefault(source.id, data)
            pages_by_container = current.setdefault("pages_by_container", {})
            pages = pages_by_container.setdefault(container_id, [])
            known_ids = {str(page.get("id", "")) for page in pages}
            pages.extend(page for page in result["pages"] if str(page.get("id", "")) not in known_ids)
            state = self._lazy_state(current, container_id)
            loaded_parents = list(state.get("loaded_parents", []))
            if parent_id not in loaded_parents:
                loaded_parents.append(parent_id)
            state["loaded_parents"] = loaded_parents
            current["pages"] = self._tree_pages(current)
            current["loaded_at"] = now_iso()
            if self._active_page_container == container_id:
                self._populate_page_tree(source, current, container_id=container_id)
            if self._active_selection_container == container_id:
                self._populate_selection_tree(source, current, container_id=container_id)
            self._refresh_pages_home()
            self._refresh_selection_home()
            suffix = " (cache local)" if result.get("from_cache") else ""
            self._set_tree_loading(False, f"{len(result['pages'])} filhos carregados{suffix}.")
            if result.get("from_cache"):
                self.statusBar().showMessage(
                    translate_text("Filhos reutilizados do cache local."), 7000
                )

        self._start_worker(work, done)

    def _populate_page_tree_lazy(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        *,
        container_id: str,
    ) -> None:
        self.page_tree.setSortingEnabled(False)
        self.page_tree.clear()
        pages = self._tree_pages(data, container_id)
        state = self._lazy_state(data, container_id)
        loaded_parents = {str(value) for value in state.get("loaded_parents", [])}
        page_ids = {str(page.get("id", "")) for page in pages if page.get("id")}
        parent_ids = parent_ids_in_list(pages)
        document_nodes: dict[str, QTreeWidgetItem] = {}

        for page in ordered_pages(pages):
            page_id = str(page.get("id", ""))
            parent_id = page_parent_id(page, page_ids)
            parent = document_nodes.get(parent_id) if parent_id else None
            visibility, visibility_kind = self._page_visibility(source, page)
            version = page.get("version", {}) or {}
            title = str(page.get("title", "Sem título"))
            raw_type = str(page.get("type", "page"))
            type_label = {"page": "Página", "folder": "Pasta", "space": "Espaço"}.get(
                raw_type.casefold(), raw_type
            )
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
            icon = "\U0001f4c1" if (page_id in parent_ids or bool(page.get("has_children"))) else "\U0001f4c4"
            item.setData(0, VisibilityBadgeDelegate.ICON_ROLE, icon)
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_ROLE, visibility)
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE, visibility_kind)
            item.setData(0, VisibilityBadgeDelegate.SOURCE_ROLE, source.id)
            item.setData(0, VisibilityBadgeDelegate.CONTAINER_ROLE, container_id)
            item.setData(0, VisibilityBadgeDelegate.DOCUMENT_ROLE, page_id)
            item.setData(0, SortableTreeItem.SORT_ROLE, title.casefold())
            (parent.addChild(item) if parent else self.page_tree.addTopLevelItem(item))
            document_nodes[page_id] = item
            # Root pages are conservatively expandable when the roots endpoint
            # omits children metadata. Expanding them still performs the child
            # request on demand; no descendants are prefetched here.
            if (
                (not parent_id or bool(page.get("has_children")))
                and page_id not in loaded_parents
            ):
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

        self.page_tree.setSortingEnabled(False)
        self.page_tree.setProperty("_alquimista_sort_column", -1)
        self.page_tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = self.page_tree.header()
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
        self.tree_empty.setVisible(False)
        self._refresh_page_summary(source, {**data, "pages": pages})
        self.page_render_status.setText(
            translate_text(
                "Mostrando {count:,} páginas carregadas. "
                "Expanda uma pasta ou página-pai para buscar os filhos."
            ).format(count=len(pages))
        )
        self.page_load_more_button.setVisible(False)

    def _populate_page_tree(
        self,
        source: SourceConfig,
        data: dict[str, Any],
        *,
        container_id: str | None = None,
    ) -> None:
        sorting = self.page_tree.isSortingEnabled()
        self.page_tree.setSortingEnabled(False)
        self.page_tree.clear()
        root_id = str(data["root"]["id"])
        all_pages = ordered_pages(self._tree_pages(data, container_id))
        key = self._page_render_key(source, str(container_id or ""))
        limit = self._page_render_limits.get(key, 800)
        pages = all_pages[:limit]
        page_parent_ids = parent_ids_in_list(pages)
        if container_id and self._lazy_state(data, container_id).get("enabled"):
            self.page_tree.setSortingEnabled(sorting)
            self._populate_page_tree_lazy(source, data, container_id=str(container_id))
            return
        rich_rows = False
        page_ids = {str(page.get("id") or "") for page in pages if page.get("id")}
        document_nodes: dict[str, QTreeWidgetItem] = {}
        parent_by_page: dict[str, str | None] = {}

        def ancestor_chain(page: dict[str, Any]) -> list[dict[str, Any]]:
            ancestors = list(page.get("ancestors", []) or [])
            ids = [str(item.get("id")) for item in ancestors if isinstance(item, dict)]
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
            visibility, visibility_kind = self._page_visibility(source, page)
            title = str(page.get("title", "Sem título"))
            raw_type = str(page.get("type", "page"))
            type_label = {"page": "Página", "folder": "Pasta", "space": "Espaço"}.get(
                raw_type.casefold(), raw_type
            )
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
                int(page["id"]) if str(page.get("id", "")).isdigit() else str(page.get("id", "")),
                (parts[0] if parts else "Página raiz").casefold(),
                " > ".join(parts).casefold(),
                int(version.get("number", 0) or 0),
                timestamp_sort_value(str(version.get("when", ""))),
            ]
            for column, value in enumerate(sort_values):
                item.setData(column, SortableTreeItem.SORT_ROLE, value)
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_ROLE, visibility)
            item.setData(0, VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE, visibility_kind)
            item.setData(0, VisibilityBadgeDelegate.TITLE_ROLE, title)
            legacy_icon = "\U0001f4c1" if str(page.get("id", "")) in page_parent_ids else "\U0001f4c4"
            item.setData(0, VisibilityBadgeDelegate.ICON_ROLE, legacy_icon)
            item.setData(0, VisibilityBadgeDelegate.SOURCE_ROLE, source.id)
            item.setData(0, VisibilityBadgeDelegate.CONTAINER_ROLE, str(container_id or ""))
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
                parent_node: QTreeWidgetItem | None = hierarchy_nodes.get(ancestor_id)
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
                    parent_node.setData(0, VisibilityBadgeDelegate.TITLE_ROLE, ancestor_title)
                    parent_node.setData(0, VisibilityBadgeDelegate.ICON_ROLE, "📁")
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
                        self.page_tree.addTopLevelItem(parent_node)
                    else:
                        anchor.addChild(parent_node)
                    hierarchy_nodes[ancestor_id] = parent_node
                anchor = parent_node
            parent = anchor or hierarchy_nodes.get(parent_by_page.get(page_id) or "")
            if parent is None:
                self.page_tree.addTopLevelItem(document_item)
            else:
                parent.addChild(document_item)
        self.page_tree.setSortingEnabled(False)
        self.page_tree.setProperty("_alquimista_sort_column", -1)
        self.page_tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = self.page_tree.header()
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
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


    def _load_markdown_controls(self) -> None:
        for key, control in self.md_controls.items():
            value = getattr(self.project.markdown, key)
            blocker = QSignalBlocker(control)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(value))
            elif isinstance(control, QComboBox):
                index = control.findData(str(value))
                if index >= 0:
                    control.setCurrentIndex(index)
                else:
                    control.setCurrentText(str(value))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif isinstance(control, QLineEdit):
                control.setText(str(value))
            del blocker
        self._update_preview()

    def _sync_markdown_controls(self) -> None:
        data = self.project.markdown.model_dump()
        for key, control in self.md_controls.items():
            if isinstance(control, QCheckBox):
                data[key] = control.isChecked()
            elif isinstance(control, QComboBox):
                data[key] = (
                    control.currentData()
                    if control.currentData() is not None
                    else control.currentText()
                )
            elif isinstance(control, QSpinBox):
                data[key] = control.value()
            elif isinstance(control, QLineEdit):
                data[key] = control.text()
        self.project.markdown = MarkdownOptions.model_validate(data)

    def _apply_preset(self, name: str) -> None:
        self.project.markdown = MarkdownOptions.preset(name)
        self._load_markdown_controls()
        self.mark_dirty()

    def _schedule_preview(self, *_args: Any) -> None:
        self.preview_timer.start()
        self.mark_dirty()

    def _update_preview(self) -> None:
        try:
            self._sync_markdown_controls()
            source = self.project.sources[0] if self.project.sources else SourceConfig(name="Exemplo")
            root = {
                "id": "100",
                "title": "Manual do Produto",
                "space": {"key": source.space_key or "EXEMPLO", "name": source.space_name or "Exemplo"},
            }
            fake = _PreviewClient(source)
            page = sample_page()
            transformer = MarkdownTransformer(fake, source, root, self.project.markdown)
            technical = transformer.technical_markdown(page)
            metadata = page_metadata(page, source, root)
            content_hash = sha256_text(transformer.hash_input(metadata, technical))
            rendered = transformer.full_document(
                metadata, technical, content_hash, "2026-07-26T15:00:00-03:00", "preview"
            )
            self._preview_after_raw = rendered
            self._render_preview_mode()
        except Exception as exc:
            self.preview_after.setPlainText(f"Não foi possível gerar a prévia:\n{exc}")

    def _render_preview_mode(self, *_args: Any) -> None:
        if not hasattr(self, "preview_mode"):
            return
        reading = self.preview_mode.currentData() == "reading"
        if reading:
            self.preview_after.setMarkdown(self._preview_after_raw)
        else:
            self.preview_after.setPlainText(self._preview_after_raw)

    def _update_extraction_summary(self) -> None:
        if not hasattr(self, "extraction_summary"):
            return
        active = [source for source in self.project.sources if source.enabled]
        selected = sum(len(source.selected_page_ids) for source in active)
        self.extraction_summary.setText(
            translate_text(
                "🔌 {sources} fontes ativas    •    📄 {selected} páginas selecionadas\n"
                "📁 Saída: {output}\n"
                "🛡 A versão anterior será preservada se uma atualização falhar."
            ).format(sources=len(active), selected=selected, output=self.project.output_dir)
        )

    def _update_output_preview(self, *_args: Any) -> None:
        if not hasattr(self, "output_path_status"):
            return
        raw = self.output_dir.text().strip()
        if not raw:
            self.output_path_status.setText(
                translate_text(
                    "Aguardando uma pasta. Use “Escolher pasta” para evitar erros de digitação."
                )
            )
            self.output_structure.setText("")
            return
        path = Path(raw).expanduser()
        nearest = path if path.exists() else path.parent
        writable = nearest.exists() and os.access(nearest, os.W_OK)
        if writable:
            try:
                free_gb = shutil.disk_usage(nearest).free / (1024**3)
                self.output_path_status.setText(
                    translate_text("Pasta disponível para gravação · {free:.1f} GB livres").format(
                        free=free_gb
                    )
                )
            except OSError:
                self.output_path_status.setText(
                    translate_text("Pasta disponível para gravação.")
                )
        else:
            self.output_path_status.setText(
                translate_text(
                    "Não foi possível confirmar permissão de gravação. Escolha outra pasta "
                    "ou verifique o acesso no Windows."
                )
            )
        root = path.name or "ALQuimista"
        execution = "Extracao-AAAA-MM-DD" if self.output_subfolder.isChecked() else root
        self.output_structure.setText(
            translate_text(
                "Estrutura prevista\n"
                "{execution}\n"
                "  ├─ {pages_subdir}  (arquivos Markdown individuais)\n"
                "  ├─ {output_subdir}  (pacotes consolidados)\n"
                "  ├─ manifesto_alquimista.json\n"
                "  └─ relatorio_execucao.json"
            ).format(
                execution=execution,
                pages_subdir=self.project.extraction.pages_subdir,
                output_subdir=self.project.consolidation.output_subdir,
            )
        )

    def _refresh_review_legacy(self) -> None:
        if not hasattr(self, "review_summary"):
            return
        self._sync_project_ui(strict=False)
        active = [source for source in self.project.sources if source.enabled]
        selected = sum(len(source.selected_page_ids) for source in active)
        source = active[0] if active else None
        access = (
            "Sem login — somente páginas públicas"
            if source and source.auth_mode == AuthMode.PUBLIC
            else f"Conta autenticada: {(source.username or 'sessão do navegador') if source else 'não configurada'}"
        )
        estimate = len(self.last_consolidation_preview)
        operation = (
            self.execution_mode.currentText()
            if hasattr(self, "execution_mode")
            else "Extrair e consolidar"
        )
        self.review_summary.setText(
            f"Fonte\n{source.base_url if source else 'Nenhuma fonte ativa'}\n\n"
            f"Modo de acesso\n{access}\n\n"
            f"Conteúdo\n{selected} páginas selecionadas\n\n"
            f"Operação\n{operation}\n\n"
            f"Formato\n{self.project.markdown.metadata_style} · predefinição personalizada\n\n"
            f"Consolidação\n{self.con_group.currentText()} · "
            f"até {self.project.consolidation.max_pages} páginas · "
            f"até {self.project.consolidation.max_chars:,} caracteres\n\n"
            f"Arquivos estimados\n{estimate if estimate else 'Gerar prévia na etapa Consolidação'}\n\n"
            f"Pasta de saída\n{self.project.output_dir}".replace(",", ".")
        )


    def _prepare_runtimes(
        self, project: ProjectConfig, token: CancellationToken, log: Any
    ) -> list[SourceRuntime]:
        return prepare_runtimes(self, project, token, log)

    def _validated_project_snapshot(self) -> ProjectConfig | None:
        return validated_project_snapshot(self)

    def run_extraction(
        self, *, partial_update_keys: set[str] | None = None
    ) -> None:
        run_extraction(self, partial_update_keys=partial_update_keys)

    def execute_selected_operation(self) -> None:
        execute_selected_operation(self)

    def retry_failures(self) -> None:
        retry_failures(self)

    def run_complete(self) -> None:
        run_complete(self)


    def _update_consolidation_action_availability(self) -> None:
        if not hasattr(self, "preview_consolidation_button"):
            return
        active = [source for source in self.project.sources if source.enabled]
        has_selection = any(
            self.project.selected_keys_for(source.id) for source in active
        )
        ready = has_selection and self.worker is None
        self.preview_consolidation_button.setEnabled(ready)
        self.generate_consolidation_button.setEnabled(ready)

    def _sync_consolidation_ui(self) -> None:
        if not hasattr(self, "con_group"):
            return
        index = self.con_group.findData(self.project.consolidation.grouping)
        self.con_group.setCurrentIndex(max(index, 0))
        self.con_pages.setValue(self.project.consolidation.max_pages)
        self.con_chars.setValue(self.project.consolidation.max_chars)
        self.con_depth.setValue(self.project.consolidation.module_depth)
        depth_index = self.con_depth_choice.findData(self.project.consolidation.module_depth)
        if depth_index >= 0:
            blocker = QSignalBlocker(self.con_depth_choice)
            self.con_depth_choice.setCurrentIndex(depth_index)
            del blocker
        self.con_prefix.setText(self.project.consolidation.filename_prefix)
        self.con_hierarchy.setChecked(self.project.consolidation.include_hierarchy_headings)
        self._update_consolidation_summary()

    def _sync_consolidation_controls(self) -> None:
        if not hasattr(self, "con_group"):
            return
        self.project.consolidation.grouping = cast(Any, str(self.con_group.currentData()))
        self.project.consolidation.max_pages = self.con_pages.value()
        self.project.consolidation.max_chars = self.con_chars.value()
        depth = self.con_depth.value()
        depth_index = self.con_depth_choice.findData(depth)
        if depth_index >= 0 and self.con_depth_choice.currentIndex() != depth_index:
            blocker = QSignalBlocker(self.con_depth_choice)
            self.con_depth_choice.setCurrentIndex(depth_index)
            del blocker
        self.project.consolidation.module_depth = depth
        self.project.consolidation.filename_prefix = self.con_prefix.text()
        self.project.consolidation.include_hierarchy_headings = self.con_hierarchy.isChecked()

    def _depth_choice_changed(self, *_args: Any) -> None:
        if not hasattr(self, "con_depth_choice"):
            return
        value = self.con_depth_choice.currentData()
        if value is None:
            return
        blocker = QSignalBlocker(self.con_depth)
        self.con_depth.setValue(int(value))
        del blocker
        self._update_consolidation_summary()
        self._mark_consolidation_preview_stale()

    def _consolidation_example_paths(self, limit: int = 6) -> list[list[str]]:
        examples: list[list[str]] = []
        for source in self.project.sources:
            if not source.enabled:
                continue
            data = self.trees.get(source.id) or {}
            selected_ids = set(source.selected_page_ids)
            pages = self._tree_pages(data)
            for page in pages:
                page_id = str(page.get("id", ""))
                if selected_ids and page_id not in selected_ids:
                    continue
                path = [str(part) for part in page.get("path", []) or [] if str(part).strip()]
                if not path:
                    ancestors = page.get("ancestors", []) or []
                    path = [
                        str(ancestor.get("title", ""))
                        for ancestor in ancestors
                        if str(ancestor.get("title", "")).strip()
                    ]
                    path.append(str(page.get("title", "Sem título")))
                if len(path) > 1 and path[0] == str((page.get("space") or {}).get("name", "")):
                    path = path[1:]
                if path not in examples:
                    examples.append(path)
                if len(examples) >= limit:
                    return examples
        if examples:
            return examples
        return [
            ["Acesso ao Sistema", "Barra de Cabeçalho", "Login"],
            ["Acesso ao Sistema", "Barra de Cabeçalho", "Dashboard"],
            ["Cadastros", "Clientes", "Novo cliente"],
        ][:limit]

    def _update_depth_examples(self) -> None:
        if not hasattr(self, "con_depth_choice"):
            return
        level = int(self.con_depth_choice.currentData() or self.con_depth.value())
        paths = self._consolidation_example_paths()
        lines = []
        for path in paths[:4]:
            hierarchy = path[:-1] or path[:1]
            group = " › ".join(hierarchy[:level])
            lines.append(f"• {group}  →  {path[-1]}")
        self.con_depth_example.setText(
            translate_text(
                "Exemplo no nível {level}: os pacotes serão agrupados por "
                "{level} nível(is) da árvore.\n{lines}"
            ).format(level=level, lines="\n".join(lines))
        )
        self.con_depth_preview.setText(
            translate_text("Como ficará no nível {level}:\n{lines}").format(
                level=level, lines="\n".join(lines)
            )
        )

    def _update_consolidation_summary(self, *_args: Any) -> None:
        if not hasattr(self, "con_summary"):
            return
        help_text = {
            "module": (
                translate_text(
                    "Separa os pacotes pelos módulos da árvore. Use a profundidade abaixo "
                    "para escolher quantos níveis entram em cada grupo."
                )
            ),
            "module_submodule": (
                translate_text(
                    "Separa pelo primeiro e segundo níveis da árvore, sem depender do campo "
                    "de profundidade."
                )
            ),
            "source_module": translate_text(
                "Separa por fonte e primeiro módulo; útil para várias fontes."
            ),
        }.get(
            str(self.con_group.currentData()),
            translate_text(
                "Define quais páginas ficam juntas e como os arquivos serão distribuídos."
            ),
        )
        self.con_group_help.setText(help_text)
        selected = sum(
            len(source.selected_page_ids)
            for source in self.project.sources
            if source.enabled
        )
        prefix = self.con_prefix.text().strip() or translate_text("pacote")
        estimate = len(self.last_consolidation_preview)
        estimate_text = str(estimate) if estimate else translate_text("calculada na prévia")
        self.con_filename_preview.setText(
            translate_text("Exemplo de arquivo: {prefix}-01.md, {prefix}-02.md").format(
                prefix=prefix
            )
        )
        self.con_summary.setText(
            translate_text(
                "📋 Resumo antes de gerar: {selected} páginas · {group} · "
                "até {pages} páginas · até {chars:,} caracteres · profundidade {depth} · "
                "saída Markdown (.md) · quantidade de arquivos: {estimate}"
            ).format(
                selected=selected,
                group=self.con_group.currentText(),
                pages=self.con_pages.value(),
                chars=self.con_chars.value(),
                depth=self.con_depth.value(),
                estimate=estimate_text,
            ).replace(",", ".")
        )
        self._update_depth_examples()

    def _mark_consolidation_preview_stale(self, *_args: Any) -> None:
        if not hasattr(self, "con_preview_status") or not self.last_consolidation_preview:
            return
        self.con_preview_status.setText(
            translate_text("○ Regras alteradas · atualize a prévia")
        )
        self.con_preview_status.setProperty("stale", True)
        self.con_preview_status.style().unpolish(self.con_preview_status)
        self.con_preview_status.style().polish(self.con_preview_status)

    def _render_consolidation_preview(self, preview: list[dict[str, Any]]) -> None:
        groups: dict[str, dict[str, int]] = {}
        total_pages = 0
        total_chars = 0
        oversized = 0
        for item in preview:
            group = str(item.get("group") or "Sem grupo")
            summary = groups.setdefault(group, {"packages": 0, "pages": 0, "characters": 0})
            summary["packages"] += 1
            summary["pages"] += int(item.get("pages", 0))
            summary["characters"] += int(item.get("characters", 0))
            total_pages += int(item.get("pages", 0))
            total_chars += int(item.get("characters", 0))
            oversized += int(bool(item.get("oversized")))

        self.package_table.setRowCount(len(groups))
        for row, (group, values) in enumerate(groups.items(), 1):
            cells = [
                str(row),
                group,
                str(values["packages"]),
                str(values["pages"]),
                f"{values['characters']:,}".replace(",", "."),
            ]
            for column, value in enumerate(cells):
                self.package_table.setItem(row - 1, column, QTableWidgetItem(value))

        package_count = len(preview)
        self.con_stat_labels["packages"].setText(str(package_count))
        self.con_stat_labels["pages"].setText(f"{total_pages:,}".replace(",", "."))
        self.con_stat_labels["characters"].setText(f"{total_chars:,}".replace(",", "."))
        average = round(total_pages / package_count) if package_count else 0
        self.con_stat_labels["average"].setText(str(average))
        self.con_distribution_title.setText(
            translate_text("Distribuição por grupo ({count} grupos)").format(
                count=len(groups)
            )
        )
        self.package_table.setVisible(bool(groups))
        self.con_preview_empty.setVisible(not bool(groups))
        if oversized:
            self.con_preview_status.setText(
                translate_text(
                    "⚠  Prévia atualizada · {count} pacote(s) acima do limite"
                ).format(count=oversized)
            )
        else:
            self.con_preview_status.setText(translate_text("● Prévia atualizada agora"))
        self.con_preview_status.setProperty("stale", False)
        self.con_preview_status.style().unpolish(self.con_preview_status)
        self.con_preview_status.style().polish(self.con_preview_status)

    def preview_consolidation(self) -> None:
        snapshot = self._validated_project_snapshot()
        if snapshot is None:
            return

        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> list[dict[str, Any]]:
            progress(0, 1, "Calculando prévia")
            preview = ConsolidationService(
                snapshot,
                self._project_dir(),
                token=token,
                log=log,
            ).preview()
            progress(1, 1, "Prévia concluída")
            return preview

        def done(preview: list[dict[str, Any]]) -> None:
            self.last_consolidation_preview = preview
            self._render_consolidation_preview(preview)
            self._update_consolidation_summary()

        self._start_worker(work, done)

    def run_consolidation(self) -> None:
        snapshot = self._validated_project_snapshot()
        if snapshot is None:
            return

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            return ConsolidationService(
                snapshot,
                self._project_dir(),
                token=token,
                log=log,
                progress=progress,
            ).run()

        self._start_worker(work, self._operation_done)

    def _start_worker(self, function: Any, done: Any) -> None:
        self.operation_controller.start(function, done)

    def _on_progress(self, done: int, total: int, item: str) -> None:
        self.operation_controller.on_progress(done, total, item)

    def _append_log(self, message: str) -> None:
        self.operation_controller.append_log(message)

    def _worker_failed(self, message: str, detail: str) -> None:
        self.operation_controller.worker_failed(message, detail)

    def _worker_finished(self) -> None:
        self.operation_controller.worker_finished()

    def cancel_operation(self) -> None:
        self.operation_controller.cancel()


    def _operation_done(self, result: dict[str, Any]) -> None:
        self.last_result = result
        self.progress.setValue(100)
        self.progress_label.setText(translate_text("Operação concluída."))
        self._refresh_results()
        self._show_page("results")
        QMessageBox.information(
            self,
            translate_text("Concluído"),
            translate_text("Operação concluída com sucesso."),
        )

    def _refresh_results(self) -> None:
        if not self.last_result:
            return
        result = self.last_result
        if "extraction" in result:
            extraction = result["extraction"]
            consolidation = result["consolidation"]
            result = {
                **extraction,
                "packages": consolidation.get("packages", 0),
                "pages_in_packages": consolidation.get("pages", 0),
                "duration_seconds": self.last_result.get("duration_seconds", 0),
            }
        lines = ["RESULTADO DA OPERAÇÃO", ""]
        if "counters" in result:
            lines.extend(
                [
                    f"Fontes processadas: {len(result.get('sources', []))}",
                    f"Páginas encontradas: {result.get('pages_found', 0)}",
                    f"Páginas selecionadas: {result.get('pages_selected', 0)}",
                ]
            )
            for key, value in result.get("counters", {}).items():
                lines.append(f"{key}: {value}")
            lines.append(f"Falhas: {result.get('failures', 0)}")
            if "packages" in result:
                lines.append(f"Pacotes gerados: {result.get('packages', 0)}")
            lines.append(f"Manifesto: {result.get('manifest', '')}")
        else:
            lines.extend(
                [
                    f"Pacotes gerados: {result.get('packages', 0)}",
                    f"Documentos: {result.get('pages', 0)}",
                ]
            )
        lines.extend(
            [
                f"Duração: {result.get('duration_seconds', 0)}s",
                f"Saída: {result.get('output_dir', '')}",
            ]
        )
        self.result_summary.setPlainText("\n".join(lines))

    def copy_report(self) -> None:
        QApplication.clipboard().setText(self.result_summary.toPlainText())
        self.statusBar().showMessage(translate_text("Relatório copiado."), 3000)

    def _base_path(self) -> Path:
        raw = Path(self.project.output_dir)
        return raw.resolve() if raw.is_absolute() else (self._project_dir() / raw).resolve()

    def open_output(self) -> None:
        path = self._base_path()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def copy_output_path(self) -> None:
        QApplication.clipboard().setText(str(self._base_path()))
        self.statusBar().showMessage(translate_text("Caminho da pasta copiado."), 3000)

    def open_manifest(self) -> None:
        path = self._base_path() / MANIFEST_NAME
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                self,
                translate_text("Manifesto"),
                translate_text("O manifesto ainda não foi criado."),
            )

    def open_log(self) -> None:
        if self.log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))
        else:
            QMessageBox.information(
                self,
                translate_text("Log técnico"),
                translate_text("O log ainda não foi criado."),
            )

    def export_report(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self, "Exportar relatório", "relatorio_alquimista.txt", "Texto (*.txt)"
        )
        if selected:
            Path(selected).write_text(self.result_summary.toPlainText(), encoding="utf-8")

    def choose_output(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Escolher pasta da base")
        if selected:
            self.output_dir.setText(selected)
            self.mark_dirty()

    def _restore_network_defaults(self) -> None:
        if (
            QMessageBox.question(
                self,
                translate_text("Restaurar valores recomendados"),
                translate_text(
                    "Restaurar timeout, tentativas e intervalo para os valores seguros padrão?"
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        defaults = default_project().extraction
        self.timeout_spin.setValue(defaults.timeout_seconds)
        self.retries_spin.setValue(defaults.retry_count)
        self.delay_spin.setValue(defaults.request_delay_ms)
        self.mark_dirty()
        self.statusBar().showMessage(
            translate_text("Valores recomendados restaurados. Salve o projeto."), 4000
        )





    def _show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if not page:
            return
        self.stack.setCurrentWidget(page)
        for name, nav in self.nav_buttons.items():
            nav.setChecked(name == key)
        if key == "dashboard":
            self._refresh_dashboard()
        elif key == "selection":
            self._selection_go_back()
        elif key == "results":
            self._refresh_results()
        elif key == "consolidation":
            self._sync_consolidation_ui()
            self._update_consolidation_action_availability()
        elif key in {"extraction", "review"}:
            self._refresh_review()
        elif key == "output":
            self._update_output_preview()

    def _refresh_dashboard(self) -> None:
        active = [source for source in self.project.sources if source.enabled]
        selected = sum(
            len(self.project.selected_keys_for(source.id)) for source in active
        )
        if hasattr(self, "dashboard_status"):
            state = translate_text("Executando" if self.worker else "Pronto")
            self.dashboard_status.setText(
                translate_text(
                    "🛡  Sua conexão é segura. {sources} fonte(s) ativa(s), "
                    "{selected} página(s) selecionada(s) — {state}."
                ).format(sources=len(active), selected=selected, state=state)
            )
        self._update_consolidation_action_availability()

    def _refresh_review(self) -> None:
        if not hasattr(self, "review_summary"):
            return
        self._sync_project_ui(strict=False)
        active = [source for source in self.project.sources if source.enabled]
        source = active[0] if active else None
        selected = sum(
            len(self.project.selected_keys_for(item.id)) for item in active
        )
        source_text = (
            f"{source.name} · Ativa" if source else "Nenhuma fonte ativa · Pendente"
        )
        if source is None:
            connection_text = "Não configurada · Pendente"
        elif source.auth_mode == AuthMode.PUBLIC:
            connection_text = (
                "Acesso público · Conectada"
                if source.id in self.connected_sources
                else "Acesso público · Pendente de teste"
            )
        elif source.id in self.connection_states:
            connection_text = self.connection_states[source.id]
        else:
            connection_text = "Não conectada · Pendente"
        selection_text = (
            f"{selected} páginas · Pronta"
            if selected
            else "0 páginas · Pendente — selecione documentos"
        )
        format_text = f"Markdown ({self.project.markdown.metadata_style}) · Configurado"
        manifest_ready = (self._base_path() / MANIFEST_NAME).is_file()
        consolidation_text = (
            f"{self.con_group.currentText()} · Pronta"
            if manifest_ready
            else f"{self.con_group.currentText()} · Pendente — manifesto ainda não criado"
        )
        output_text = self.output_dir.text().strip() or self.project.output_dir
        values = {
            "source": source_text,
            "connection": connection_text,
            "selection": selection_text,
            "format": format_text,
            "consolidation": consolidation_text,
            "operation_source": source_text,
            "operation_connection": connection_text,
            "operation_selection": selection_text,
            "operation_format": format_text,
            "operation_consolidation": consolidation_text,
            "operation_output": output_text,
        }
        for key, value in values.items():
            label = self.review_values.get(key)
            if label is not None:
                label.setText(value)
        estimate = len(self.last_consolidation_preview)
        self.review_summary.setVisible(True)
        self.review_summary.setText(
            f"Fonte\n{source_text}\n\n"
            f"Modo de acesso\n{connection_text}\n\n"
            f"Seleção\n{selection_text}\n\n"
            f"Operação\n{self.execution_mode.currentText()}\n\n"
            f"Formato\n{format_text}\n\n"
            f"Consolidação\n{consolidation_text}\n\n"
            f"Arquivos estimados\n{estimate if estimate else 'Prévia ainda não gerada'}\n\n"
            f"Pasta de saída\n{output_text}"
        )
        self._update_output_preview()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Request cancellation and wait a bounded time before closing."""
        if self.worker is not None:
            self.operation_controller.cancel(confirm=False)
            self.thread_pool.waitForDone(15000)
            if self.worker is not None:
                # The worker is cooperative. Do not leave the window blocked if
                # an external request ignored the cancellation token.
                self.worker = None
                self.token = None
                self.operation_status = "IDLE"
                if hasattr(self, "cancel_button"):
                    self.cancel_button.setEnabled(False)
                self._set_tree_loading(False, "Operação cancelada ao fechar o aplicativo.")
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
class _PreviewClient:
    def __init__(self, source: SourceConfig) -> None:
        self.source = source
        self.base_url = source.base_url


def run_app(mode: str = "complete") -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ALQuimista Studio")
    app.setOrganizationName("ALQuimista")
    from .i18n import initialize_language

    language_manager = initialize_language(app)
    apply_theme(app, "system")
    window = MainWindow(mode, language_manager)
    window.show()
    raise SystemExit(app.exec())
