from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QPropertyAnimation,
    QSize,
    Qt,
    QThreadPool,
)
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..connectors import default_registry
from ..logging_utils import configure_logging, default_log_path
from ..models import (
    AuthMode,
    ProjectConfig,
    SourceConfig,
    default_project,
    now_iso,
)
from ..runtime import CancellationToken
from ..selection import SelectionStore
from ..services import SourceRuntime
from ..storage import MANIFEST_NAME
from .components import (
    APP_TITLE,
    NAV_ICON_INDEX,
    NAVIGATION,
    AlchemistIconAtlas,
    HorizontalScrollArea,
    ResponsiveOutputControls,
    SourceCard,
    VisibilityBadgeDelegate,
    button,
    card,
    page_header,
)
from .controllers import (
    ConsolidationController,
    NavigationController,
    PreviewController,
    ResultsController,
    RuntimeSecrets,
    TreeController,
    TreeLoaderController,
    WorkerOperationController,
    execute_selected_operation,
    load_project_file,
    prepare_runtimes,
    resolve_project_dir,
    retry_failures,
    run_complete,
    run_extraction,
    save_project_file,
    validated_project_snapshot,
)
from .i18n import (
    LANGUAGE_NAMES,
    LanguageManager,
    create_settings,
    translate_text,
)
from .mixins.connection_mixin import ConnectionMixin
from .mixins.selection_mixin import SelectionMixin
from .mixins.source_mixin import SourceMixin
from .pages.connection_page import build_connection_page
from .pages.consolidation_page import build_consolidation_page
from .pages.dashboard_page import build_dashboard_page
from .pages.extraction_page import build_extraction_page
from .pages.markdown_page import build_markdown_page
from .pages.results_page import build_results_page
from .pages.review_page import build_review_page
from .pages.selection_page import build_selection_page
from .pages.sources_page import build_sources_page
from .state import MainWindowState
from .theme import apply_theme
from .tree_models import (
    page_container_id as tree_page_container_id,
)
from .tree_models import (
    tree_containers,
    tree_pages,
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
        self.operation_controller = WorkerOperationController(
            self, self.thread_pool
        )
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("MainWindow requires an active QApplication")
        self.i18n = language_manager or LanguageManager(app, create_settings())
        if language_manager is None:
            self.i18n.set_language(
                self.i18n.preferred_language or "pt-BR", persist=False
            )
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
        self.tree_controller = TreeController(
            settings=self.ui_settings,
            status_bar=self.statusBar(),
        )
        self._build()
        self._load_project_ui()
        self._update_load_context()
        self._show_page("dashboard")
        self.retranslate_ui()
        # Widget initialization can emit ordinary editor signals; loading the
        # default project is not a user edit and must leave the window clean.
        self.dirty = False
        self.project_badge.setText(translate_text("● Projeto não salvo"))

    def _language_changed(self, _language: str) -> None:
        dirty_before = self.dirty
        self.navigation_controller.language_changed(
            _language,
            window=self,
            language_combo=getattr(self, "language_combo", None),
            on_retranslate_callbacks=[
                lambda: self._refresh_dashboard(),
                lambda: self._update_preview()
                if hasattr(self, "preview_after")
                else None,
                lambda: self._update_consolidation_summary()
                if hasattr(self, "con_group")
                else None,
                lambda: self._refresh_review()
                if hasattr(self, "review_summary")
                else None,
                lambda: self._update_extraction_summary()
                if hasattr(self, "extraction_summary")
                else None,
                lambda: self._update_output_preview()
                if hasattr(self, "output_path_status")
                else None,
                lambda: self._refresh_results()
                if hasattr(self, "result_summary")
                else None,
            ],
        )
        self.dirty = dirty_before
        self.project_badge.setText(
            translate_text("● Alterações não salvas")
            if dirty_before
            else translate_text("● Projeto não salvo")
        )

    def retranslate_ui(self) -> None:
        """Refresh visible UI labels while keeping language combo data stable."""
        self.navigation_controller.retranslate_ui(
            self,
            language_combo=getattr(self, "language_combo", None),
            callbacks=[
                lambda: self._update_consolidation_summary()
                if hasattr(self, "con_group")
                else None,
                lambda: self._refresh_review()
                if hasattr(self, "review_summary")
                else None,
                lambda: self._update_extraction_summary()
                if hasattr(self, "extraction_summary")
                else None,
                lambda: self._update_output_preview()
                if hasattr(self, "output_path_status")
                else None,
                lambda: self._refresh_results()
                if hasattr(self, "result_summary")
                else None,
            ],
        )

    def _change_language(self, language: str) -> None:
        self.navigation_controller.change_language(language)

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
            nav.setIcon(
                AlchemistIconAtlas.icon(NAV_ICON_INDEX.get(key, 15), 22)
            )
            nav.setIconSize(QSize(22, 22))
            nav.setCheckable(True)
            nav.clicked.connect(
                lambda _checked=False, name=key: self._show_page(name)
            )
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
        top.setStyleSheet(
            "border-radius: 0; border-top: 0; border-left: 0; border-right: 0;"
        )
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
        self.pages["review"] = self.pages["extraction"]
        self.pages["pages"] = self._pages_page()
        self.stack.addWidget(self.pages["pages"])
        self.pages["output"] = self.pages["extraction"]
        self._init_controllers()

    def _init_controllers(self) -> None:
        self.navigation_controller = NavigationController(
            stack=self.stack,
            nav_buttons=self.nav_buttons,
            pages=self.pages,
            i18n=self.i18n,
            on_page_changed=self._on_nav_page_changed,
            op_mode_combo=getattr(self, "execution_mode", None),
            op_mode_help_label=getattr(self, "execution_mode_help", None),
        )
        self.tree_loader_controller = TreeLoaderController(
            connector_registry=self.connector_registry,
            secrets=self.secrets,
            trees=self.trees,
            worker_starter=self._start_worker,
            status_bar=self.statusBar(),
            tree_load_buttons=[
                btn
                for btn in (
                    getattr(self, "tree_load_button", None),
                    getattr(self, "selection_load_button", None),
                )
                if btn is not None
            ],
            tree_cancel_buttons=[
                btn
                for btn in (
                    getattr(self, "tree_cancel_button", None),
                    getattr(self, "selection_cancel_button", None),
                )
                if btn is not None
            ],
            tree_load_status_label=getattr(self, "tree_load_status", None),
            tree_load_progress=getattr(self, "tree_load_progress", None),
        )
        self.preview_controller = PreviewController(
            md_controls=getattr(self, "md_controls", {}),
            preview_mode_combo=getattr(self, "preview_mode", None),
            preview_editor=getattr(self, "preview_after", None),
            preview_timer=getattr(self, "preview_timer", None),
            extraction_summary_label=getattr(self, "extraction_summary", None),
            output_path_status_label=getattr(self, "output_path_status", None),
            output_structure_label=getattr(self, "output_structure", None),
            output_dir_input=getattr(self, "output_dir", None),
            output_subfolder_checkbox=getattr(self, "output_subfolder", None),
        )
        self.consolidation_controller = ConsolidationController(
            group_combo=getattr(self, "con_group", None),
            pages_spin=getattr(self, "con_pages", None),
            chars_spin=getattr(self, "con_chars", None),
            depth_spin=getattr(self, "con_depth", None),
            depth_choice_combo=getattr(self, "con_depth_choice", None),
            prefix_input=getattr(self, "con_prefix", None),
            hierarchy_checkbox=getattr(self, "con_hierarchy", None),
            summary_label=getattr(self, "con_summary", None),
            group_help_label=getattr(self, "con_group_help", None),
            depth_example_label=getattr(self, "con_depth_example", None),
            depth_preview_label=getattr(self, "con_depth_preview", None),
            filename_preview_label=getattr(self, "con_filename_preview", None),
            preview_status_label=getattr(self, "con_preview_status", None),
            package_table=getattr(self, "package_table", None),
            stat_labels=getattr(self, "con_stat_labels", {}),
            distribution_title=getattr(self, "con_distribution_title", None),
            preview_empty_widget=getattr(self, "con_preview_empty", None),
            preview_button=getattr(self, "preview_consolidation_button", None),
            generate_button=getattr(
                self, "generate_consolidation_button", None
            ),
        )
        self.results_controller = ResultsController(
            summary_widget=getattr(self, "result_summary", None),
            status_bar=self.statusBar(),
            output_dir_getter=self._project_dir,
            log_path=self.log_path,
            metric_widgets={
                "total": getattr(self, "result_metric_total", None),
                "packages": getattr(self, "result_metric_packages", None),
                "time": getattr(self, "result_metric_time", None),
                "failures": getattr(self, "result_metric_failures", None),
            },
            output_path_label=getattr(self, "result_output_path_label", None),
        )

    def _on_nav_page_changed(self, key: str) -> None:
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

    def _show_page(self, key: str) -> None:
        if hasattr(self, "navigation_controller"):
            self.navigation_controller.show_page(key)

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

    def _markdown_page(self) -> QWidget:
        return build_markdown_page(self)

    def _toggle_all_markdown_sections(self, expanded: bool) -> None:
        for current in getattr(self, "markdown_sections", []):
            current.set_expanded(expanded)

    def _extraction_page(self) -> QWidget:
        return build_extraction_page(self)

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
        self.output_subfolder = QCheckBox(
            "Criar uma subpasta para esta execução"
        )
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

    def _review_page(self) -> QWidget:
        return build_review_page(self)

    def _update_execution_mode_help(self, *_args: Any) -> None:
        if hasattr(self, "navigation_controller"):
            self.navigation_controller.update_execution_mode_help()

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
        project_actions.addWidget(
            button("📂 Abrir projeto", self.open_project)
        )
        project_actions.addWidget(
            button("💾 Salvar como", self.save_project_as, primary=True)
        )
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
            lambda _index: self._change_language(
                str(self.language_combo.currentData())
            )
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
            button(
                "↺ Restaurar valores recomendados",
                self._restore_network_defaults,
            )
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
                translate_text(
                    "Descartar as alterações que ainda não foram salvas?"
                ),
            )
            == QMessageBox.StandardButton.Yes
        )

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = default_project()
        self.selection_store = SelectionStore.from_selections(
            self.project.selections
        )
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
            self.selection_store = SelectionStore.from_selections(
                self.project.selections
            )
            self.trees.clear()
            self.secrets.clear()
            self.dirty = False
            self._load_project_ui()
            self._append_log(f"Projeto aberto: {self.project_path}")
        except Exception as exc:
            QMessageBox.critical(
                self, translate_text("Projeto inválido"), str(exc)
            )

    def save_project(self) -> bool:
        if self.project_path is None:
            self.save_project_as()
            return self.project_path is not None and not self.dirty
        try:
            self._sync_project_ui()
            save_project_file(self.project_path, self.project)
            self.dirty = False
            self.project_badge.setText(
                translate_text("● Salvo em {path}").format(
                    path=self.project_path.name
                )
            )
            self.top_project.setText(self.project.project_name)
            return True
        except Exception as exc:
            QMessageBox.critical(
                self, translate_text("Falha ao salvar"), str(exc)
            )
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
        self.selection_store = SelectionStore.from_selections(
            self.project.selections
        )
        self.top_project.setText(self.project.project_name)
        self.project_badge.setText(
            translate_text("● Salvo em {path}").format(
                path=self.project_path.name
            )
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
            translate_text("● Salvo em {path}").format(
                path=self.project_path.name
            )
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
        self.project.project_name = (
            self.project_name.text().strip() or "Projeto ALQuimista"
        )
        self.project.output_dir = (
            self.output_dir.text().strip() or "ALQuimista_Base"
        )
        self.project.extraction.timeout_seconds = self.timeout_spin.value()
        self.project.extraction.retry_count = self.retries_spin.value()
        self.project.extraction.request_delay_ms = self.delay_spin.value()
        if hasattr(self, "md_controls"):
            self._sync_markdown_controls()
        self._sync_consolidation_controls()
        return source_valid

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

    def _load_markdown_controls(self) -> None:
        if hasattr(self, "preview_controller"):
            self.preview_controller.load_markdown_controls(self.project.markdown)
            self._update_preview()

    def _sync_markdown_controls(self) -> None:
        if hasattr(self, "preview_controller"):
            self.project.markdown = (
                self.preview_controller.sync_markdown_controls(
                    self.project.markdown
                )
            )

    def _apply_preset(self, name: str) -> None:
        if hasattr(self, "preview_controller"):
            self.project.markdown = self.preview_controller.apply_preset(
                name, on_dirty=self.mark_dirty
            )
            self._update_preview()

    def _schedule_preview(self, *_args: Any) -> None:
        if hasattr(self, "preview_controller"):
            self.preview_controller.schedule_preview(on_dirty=self.mark_dirty)

    def _update_preview(self) -> None:
        if hasattr(self, "preview_controller"):
            self._sync_markdown_controls()
            self.preview_controller.update_preview(
                self.project.sources, self.project.markdown
            )

    def _render_preview_mode(self, *_args: Any) -> None:
        if hasattr(self, "preview_controller"):
            self.preview_controller.render_preview_mode()

    def _update_extraction_summary(self) -> None:
        if hasattr(self, "preview_controller"):
            self.preview_controller.update_extraction_summary(
                self.project.sources, self.project.output_dir
            )

    def _update_output_preview(self, *_args: Any) -> None:
        if (
            hasattr(self, "preview_controller")
            and hasattr(self, "output_dir")
            and hasattr(self, "output_subfolder")
        ):
            self.preview_controller.update_output_preview(
                self.output_dir.text(),
                self.project.extraction.pages_subdir,
                self.project.consolidation.output_subdir,
                use_subfolder=self.output_subfolder.isChecked(),
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
        if hasattr(self, "consolidation_controller"):
            self.consolidation_controller.update_action_availability(
                self.project, worker_running=self.worker is not None
            )

    def _sync_consolidation_ui(self) -> None:
        if hasattr(self, "consolidation_controller"):
            self.consolidation_controller.sync_ui(
                self.project.consolidation,
                self.project.sources,
                self.trees,
                self.last_consolidation_preview,
            )

    def _sync_consolidation_controls(self) -> None:
        if hasattr(self, "consolidation_controller"):
            self.project.consolidation = (
                self.consolidation_controller.sync_controls(
                    self.project.consolidation
                )
            )

    def _depth_choice_changed(self, *_args: Any) -> None:
        if hasattr(self, "consolidation_controller"):
            self.consolidation_controller.depth_choice_changed(
                self.project.sources,
                self.trees,
                self.last_consolidation_preview,
            )

    def _consolidation_example_paths(self, limit: int = 6) -> list[list[str]]:
        if hasattr(self, "consolidation_controller"):
            return self.consolidation_controller.example_paths(
                self.project.sources, self.trees, self._tree_pages, limit=limit
            )
        return []

    def _update_depth_examples(self) -> None:
        if hasattr(self, "consolidation_controller"):
            paths = self._consolidation_example_paths()
            self.consolidation_controller.update_depth_examples(paths)

    def _update_consolidation_summary(self, *_args: Any) -> None:
        if hasattr(self, "consolidation_controller"):
            self.consolidation_controller.update_summary(
                self.project.sources,
                self.trees,
                self.last_consolidation_preview,
                self._tree_pages,
            )

    def _mark_consolidation_preview_stale(self, *_args: Any) -> None:
        if hasattr(self, "consolidation_controller"):
            self.consolidation_controller.mark_preview_stale(
                self.last_consolidation_preview
            )

    def _render_consolidation_preview(
        self, preview: list[dict[str, Any]]
    ) -> None:
        if hasattr(self, "consolidation_controller"):
            self.consolidation_controller.render_preview(preview)

    def preview_consolidation(self) -> None:
        snapshot = self._validated_project_snapshot()
        if snapshot is None:
            return

        def done(preview: list[dict[str, Any]]) -> None:
            self.last_consolidation_preview = preview
            self._render_consolidation_preview(preview)
            self._update_consolidation_summary()

        self.consolidation_controller.preview_consolidation(
            snapshot, self._project_dir(), self._start_worker, done
        )

    def run_consolidation(self) -> None:
        snapshot = self._validated_project_snapshot()
        if snapshot is None:
            return

        self.consolidation_controller.run_consolidation(
            snapshot,
            self._project_dir(),
            self._start_worker,
            self._operation_done,
        )

    def _start_worker(self, function: Any, done: Any) -> None:
        self.operation_controller.start(function, done)

    def _on_progress(self, done: int, total: int, item: str) -> None:
        self.operation_controller.on_progress(done, total, item)

    def _append_log(self, message: str) -> None:
        self.operation_controller.append_log(message)

    def _worker_failed(self, error: Exception | str, detail: str) -> None:
        self.operation_controller.worker_failed(error, detail)

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
        if hasattr(self, "results_controller"):
            self.results_controller.refresh_results(self.last_result)

    def copy_report(self) -> None:
        self.results_controller.copy_report()

    def _base_path(self) -> Path:
        return self.results_controller.base_path()

    def open_output(self) -> None:
        self.results_controller.open_output()

    def copy_output_path(self) -> None:
        self.results_controller.copy_output_path()

    def open_manifest(self) -> None:
        self.results_controller.open_manifest(self)

    def open_log(self) -> None:
        self.results_controller.open_log(self)

    def export_report(self) -> None:
        self.results_controller.export_report(self)

    def choose_output(self) -> None:
        def on_chosen(selected: str) -> None:
            self.output_dir.setText(selected)
            self.mark_dirty()

        self.results_controller.choose_output(self, on_chosen)

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
            translate_text("Valores recomendados restaurados. Salve o projeto."),
            4000,
        )

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
            translate_text("{name} · Ativa").format(name=source.name)
            if source
            else translate_text("Nenhuma fonte ativa · Pendente")
        )
        if source is None:
            connection_text = translate_text("Não configurada · Pendente")
        elif source.auth_mode == AuthMode.PUBLIC:
            connection_text = (
                translate_text("Acesso público · Conectada")
                if source.id in self.connected_sources
                else translate_text("Acesso público · Pendente de teste")
            )
        elif source.id in self.connection_states:
            connection_text = self.connection_states[source.id]
        else:
            connection_text = translate_text("Não conectada · Pendente")
        selection_text = (
            translate_text("{count} páginas · Pronta").format(count=selected)
            if selected
            else translate_text("0 páginas · Pendente — selecione documentos")
        )
        format_text = translate_text(
            "Markdown ({style}) · Configurado"
        ).format(style=self.project.markdown.metadata_style)
        manifest_ready = (self._base_path() / MANIFEST_NAME).is_file()
        consolidation_text = (
            translate_text("{group} · Pronta").format(
                group=self.con_group.currentText()
            )
            if manifest_ready
            else translate_text(
                "{group} · Pendente — manifesto ainda não criado"
            ).format(group=self.con_group.currentText())
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
            f"{translate_text('Fonte')}\n{source_text}\n\n"
            f"{translate_text('Modo de acesso')}\n{connection_text}\n\n"
            f"{translate_text('Seleção')}\n{selection_text}\n\n"
            f"{translate_text('Operação')}\n{self.execution_mode.currentText()}\n\n"
            f"{translate_text('Formato')}\n{format_text}\n\n"
            f"{translate_text('Consolidação')}\n{consolidation_text}\n\n"
            f"{translate_text('Arquivos estimados')}\n"
            f"{estimate if estimate else translate_text('Prévia ainda não gerada')}\n\n"
            f"{translate_text('Pasta de saída')}\n{output_text}"
        )
        self._update_output_preview()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Request cancellation and wait a bounded time before closing."""
        if self.worker is not None:
            self.operation_controller.cancel(confirm=False)
            self.thread_pool.waitForDone(15000)
            if self.worker is not None:
                self.worker = None
                self.token = None
                self.operation_status = "IDLE"
                if hasattr(self, "cancel_button"):
                    self.cancel_button.setEnabled(False)
                self._set_tree_loading(
                    False, "Operação cancelada ao fechar o aplicativo."
                )
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()


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


__all__ = ["MainWindow", "run_app"]
