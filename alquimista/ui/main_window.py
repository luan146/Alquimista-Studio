from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QPropertyAnimation,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
)
from PySide6.QtGui import QCloseEvent, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..connectors import default_registry
from ..logging_utils import configure_logging, default_log_path
from ..models import (
    AuthMode,
    ProjectConfig,
    default_project,
)
from ..runtime import CancellationToken
from ..selection import SelectionStore
from ..services import SourceRuntime
from ..storage import MANIFEST_NAME
from .components import (
    APP_TITLE,
    NAV_ICON_INDEX,
    NAVIGATION,
    PAGE_ALIASES,
    AlchemistIconAtlas,
    button,
    card,
    inform,
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
    schedule_controller,
    sync_project,
    sync_selection,
    sync_source,
    validated_project_snapshot,
)
from .i18n import (
    LanguageManager,
    create_settings,
    translate_text,
)
from .mixins.connection_mixin import ConnectionMixin
from .mixins.pages_browser_mixin import PagesBrowserMixin
from .mixins.selection_mixin import SelectionMixin
from .mixins.source_mixin import SourceMixin
from .mixins.tree_loading_mixin import TreeLoadingMixin
from .mixins.ux_mixin import UxMixin
from .mixins.workflow_mixin import WorkflowMixin
from .pages.format_page import build_format_page
from .pages.home_page import build_home_page
from .pages.results_page import build_results_page
from .pages.review_page import build_review_page
from .pages.selection_page import build_selection_page
from .pages.settings_page import build_settings_page
from .pages.sources_page import build_sources_page
from .recent_projects import recent_projects
from .state import MainWindowState
from .theme import apply_theme
from .workers import Worker


class MainWindow(
    UxMixin,
    WorkflowMixin,
    ConnectionMixin,
    SourceMixin,
    SelectionMixin,
    PagesBrowserMixin,
    TreeLoadingMixin,
    QMainWindow,
):
    # Widgets assigned by the page builders in ui/pages/.
    progress: QProgressBar
    progress_label: QLabel
    con_group: QComboBox
    execution_mode: QComboBox
    review_values: dict[str, Any]
    output_dir: QLineEdit
    project_name: QLineEdit
    timeout_spin: QSpinBox
    retries_spin: QSpinBox
    delay_spin: QSpinBox
    parallel_spin: QSpinBox
    schedule_status: QLabel
    schedule_time: QTimeEdit
    results_empty: QFrame
    results_body: QWidget

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
        self.nav_status: dict[str, QLabel] = {}
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
        self.visual_profile_combo = QComboBox()
        self.visual_profile_combo.addItem("Atelier", "atelier")
        self.visual_profile_combo.addItem("Legado", "legacy")
        saved_profile = str(
            self.ui_settings.value("preferences/visual_profile", "atelier")
            or "atelier"
        )
        profile_idx = self.visual_profile_combo.findData(saved_profile)
        self.visual_profile_combo.setCurrentIndex(max(0, profile_idx))
        self.visual_profile_combo.currentIndexChanged.connect(
            self._visual_profile_changed
        )
        apply_theme(QApplication.instance(), self._theme_preference())
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
                lambda: self._refresh_source_table()
                if hasattr(self, "source_table")
                else None,
                self._refresh_workflow_state,
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
                self._refresh_workflow_state,
            ],
        )

    def _change_language(self, language: str) -> None:
        self.navigation_controller.change_language(language)

    @property
    def _tree_loading(self) -> bool:
        return bool(
            getattr(self, "tree_loader_controller", None)
            and self.tree_loader_controller.loading
        )

    @_tree_loading.setter
    def _tree_loading(self, value: bool) -> None:
        if hasattr(self, "tree_loader_controller"):
            self.tree_loader_controller.loading = value

    @property
    def visual_profile(self) -> str:
        return str(
            getattr(self, "visual_profile_combo", None)
            and self.visual_profile_combo.currentData()
            or "atelier"
        )

    def _visual_profile_changed(self, *_args: Any) -> None:
        profile = self.visual_profile
        self.ui_settings.setValue("preferences/visual_profile", profile)
        self.ui_settings.sync()
        if QApplication.instance():
            apply_theme(QApplication.instance(), self._theme_preference())

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
        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setText("«")
        self.sidebar_toggle.setToolTip("Recolher barra lateral")
        self.sidebar_toggle.setAutoRaise(True)
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        brand_row.addWidget(self.sidebar_toggle)
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
            if key != "dashboard":
                status = QLabel("○", nav)
                status.setObjectName("navStepStatus")
                status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                nav_layout = QHBoxLayout(nav)
                nav_layout.setContentsMargins(0, 0, 12, 0)
                nav_layout.addStretch()
                nav_layout.addWidget(status)
                self.nav_status[key] = status
            self.nav_buttons[key] = nav
            side.addWidget(nav)
        side.addStretch()
        self.project_badge = QLabel("● Projeto não salvo")
        self.project_badge.setObjectName("subtitle")
        side.addWidget(self.project_badge)
        self.sidebar = sidebar
        self.sidebar_texts = [brand, tagline, self.project_badge]
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
        self.project_menu_button = QToolButton()
        self.project_menu_button.setToolTip("Novo, abrir, recentes e salvar como")
        self.project_menu_button.setText("📁 ▾")
        self.project_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.project_menu_button.clicked.connect(
            lambda: self._project_menu().exec(
                self.project_menu_button.mapToGlobal(self.project_menu_button.rect().bottomLeft())
            )
        )
        top_layout.addWidget(self.project_menu_button)
        self.top_project = QLabel(self.project.project_name)
        self.top_project.setStyleSheet("font-weight: 700;")
        top_layout.addWidget(self.top_project)
        top_layout.addStretch()
        settings_button = button(
            "Configurações", lambda: self._show_page("settings")
        )
        settings_button.setIcon(AlchemistIconAtlas.icon(8, 22))
        settings_button.setIconSize(QSize(22, 22))
        top_layout.addWidget(settings_button)
        save_button = button("Salvar", self.save_project, primary=True)
        save_button.setToolTip("Salvar o projeto (Ctrl+S)")
        save_button.setIcon(AlchemistIconAtlas.icon(9, 22))
        save_button.setIconSize(QSize(22, 22))
        top_layout.addWidget(save_button)
        content.addWidget(top)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setStyleSheet(
            "QFrame#banner { background: rgba(66, 184, 190, 0.16); border: 1px solid #42B8BE;"
            " border-radius: 8px; }"
            "QFrame#banner[kind=\"success\"] { background: rgba(127, 228, 181, 0.16); border-color: #3FB984; }"
            "QFrame#banner[kind=\"warning\"] { background: rgba(240, 180, 80, 0.16); border-color: #D9A441; }"
        )
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(14, 8, 8, 8)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        banner_layout.addWidget(self.banner_label, 1)
        self.banner_action = QPushButton()
        self.banner_action.setVisible(False)
        self.banner_action.clicked.connect(self._banner_action_clicked)
        banner_layout.addWidget(self.banner_action)
        banner_close = QToolButton()
        banner_close.setText("✕")
        banner_close.setAutoRaise(True)
        banner_close.setToolTip("Fechar aviso")
        banner_close.clicked.connect(lambda: self.banner.hide())
        banner_layout.addWidget(banner_close)
        self.banner.hide()
        banner_holder = QVBoxLayout()
        banner_holder.setContentsMargins(22, 8, 22, 0)
        banner_holder.addWidget(self.banner)
        content.addLayout(banner_holder)
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        self.step_footer = QFrame()
        self.step_footer.setObjectName("card")
        self.step_footer.setStyleSheet(
            "border-radius: 0; border-bottom: 0; border-left: 0; border-right: 0;"
        )
        footer_layout = QHBoxLayout(self.step_footer)
        footer_layout.setContentsMargins(22, 8, 22, 8)
        self.step_back_button = button("Voltar", lambda: self._go_step("back"))
        self.step_next_button = button("Próximo", lambda: self._go_step("next"), primary=True)
        for step_button in (self.step_back_button, self.step_next_button):
            step_button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            step_button.setMinimumWidth(220)
        footer_layout.addWidget(self.step_back_button)
        footer_layout.addStretch()
        footer_layout.addWidget(self.step_next_button)
        content.addWidget(self.step_footer)
        outer.addLayout(content, 1)

        format_page, markdown_tab, packages_tab = build_format_page(self)
        builders = {
            "dashboard": self._dashboard_page,
            "sources": self._sources_page,
            "selection": self._selection_page,
            "format": lambda: format_page,
            "extraction": self._review_page,
            "results": self._results_page,
        }
        for key in (item[0] for item in NAVIGATION):
            page = builders[key]()
            self.pages[key] = page
            self.stack.addWidget(page)
        settings_page = self._settings_page()
        self.pages["settings"] = settings_page
        self.stack.addWidget(settings_page)
        self.pages["pages"] = self._pages_page()
        self.stack.addWidget(self.pages["pages"])
        # Old keys keep working for code and tests that still use them.
        self.pages["markdown"] = markdown_tab
        self.pages["consolidation"] = packages_tab
        for alias, (target, _tab) in PAGE_ALIASES.items():
            self.pages.setdefault(alias, self.pages[target])
        self._init_controllers()
        self._install_shortcuts()
        self.setAcceptDrops(True)

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
            connector_registry=lambda: self.connector_registry,
            secrets=lambda: self.secrets,
            trees=lambda: self.trees,
            worker_starter=lambda fn, done: self._start_worker(fn, done),
            lazy_discovery_page=lambda *args, **kwargs: self._lazy_discovery_page(
                *args, **kwargs
            ),
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
            output_dir_getter=self._output_path,
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
            if sys.platform == "win32" and self.project_path is not None:
                schedule_controller.refresh_home_schedule(self)
        elif key == "selection":
            self._selection_go_back()
            self._maybe_autoload_tree()
        elif key == "results":
            self._refresh_results()
        elif key == "format":
            self._sync_consolidation_ui()
            self._update_consolidation_action_availability()
        elif key == "extraction":
            self._refresh_review()
            self._update_output_preview()
        elif key == "settings" and sys.platform == "win32":
            schedule_controller.refresh_schedule_status(self)
        self._refresh_workflow_state()

    def _show_page(self, key: str) -> None:
        target, tab = PAGE_ALIASES.get(key, (key, None))
        if tab is not None and hasattr(self, "format_tabs"):
            self.format_tabs.setCurrentIndex(tab)
        if hasattr(self, "navigation_controller"):
            self.navigation_controller.show_page(target)

    def _dashboard_page(self) -> QWidget:
        return build_home_page(self)

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

    def _sources_page(self) -> QWidget:
        return build_sources_page(self)

    def _selection_page(self) -> QWidget:
        return build_selection_page(self)

    def _toggle_all_markdown_sections(self, expanded: bool) -> None:
        for current in getattr(self, "markdown_sections", []):
            current.set_expanded(expanded)

    def _results_page(self) -> QWidget:
        return build_results_page(self)

    def _review_page(self) -> QWidget:
        return build_review_page(self)

    def _update_execution_mode_help(self, *_args: Any) -> None:
        if hasattr(self, "navigation_controller"):
            self.navigation_controller.update_execution_mode_help()

    def _settings_page(self) -> QWidget:
        return build_settings_page(self)

    def _set_metric(self, frame: QFrame, value: str) -> None:
        for label in frame.findChildren(QLabel):
            if label.objectName() == "metric":
                label.setText(value)
                return

    def mark_dirty(self) -> None:
        self.dirty = True
        self.project_badge.setText(translate_text("● Alterações não salvas"))
        self._schedule_workflow_refresh()

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
        self._load_project_file_into_window(Path(selected))

    def _load_project_file_into_window(self, path: Path) -> bool:
        try:
            candidate_path = path.resolve()
            candidate_project = load_project_file(candidate_path)
        except Exception as exc:
            self._confirm_open_failure(path, exc)
            return False
        self.project_path = candidate_path
        self.project = candidate_project
        self.selection_store = SelectionStore.from_selections(
            self.project.selections
        )
        self.trees.clear()
        self.secrets.clear()
        self.secrets.load_remembered(self.project.sources, self._append_log)
        self.last_result = {}
        self.dirty = False
        self._load_project_ui()
        self._remember_current_project()
        self._append_log(f"Projeto aberto: {self.project_path}")
        self._show_page("dashboard")
        return True

    def reopen_last_project(self) -> None:
        """Startup: continue where the user stopped."""
        recent = recent_projects(self.ui_settings)
        if recent:
            self._load_project_file_into_window(recent[0])

    def save_project(self) -> bool:
        if self.project_path is None:
            self.save_project_as()
            return self.project_path is not None and not self.dirty
        try:
            self._sync_project_ui()
            save_project_file(self.project_path, self.project)
            self._remember_current_project()
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

    def _output_path(self) -> Path:
        """Where extraction writes manifest, report and Markdown (project dir / output dir)."""
        output = Path(self.project.output_dir)
        return output if output.is_absolute() else self._project_dir() / output

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
        self.parallel_spin.setValue(self.project.extraction.parallel_downloads)
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
        self.project.extraction.parallel_downloads = self.parallel_spin.value()
        if hasattr(self, "md_controls"):
            self._sync_markdown_controls()
        self._sync_consolidation_controls()
        return source_valid

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
        ):
            self.preview_controller.update_output_preview(
                self.output_dir.text(),
                self.project.extraction.pages_subdir,
                self.project.consolidation.output_subdir,
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

    def sync_source(self, source_id: str) -> None:
        sync_source(self, source_id)

    def sync_project(self) -> None:
        sync_project(self)

    def sync_selection(self) -> None:
        sync_selection(self)


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
            self._update_depth_examples()

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
        self._notify_finished(
            translate_text("ALQuimista: operação concluída"),
            translate_text("Abra o ALQuimista para ver o resultado."),
        )
        inform(
            self,
            translate_text("Concluído"),
            translate_text("Operação concluída com sucesso."),
        )

    def _refresh_results(self) -> None:
        if not hasattr(self, "results_controller"):
            return
        # After reopening a project the last run comes from its report on disk.
        report = self.last_result or self._last_report()
        self.results_empty.setVisible(not report)
        self.results_body.setVisible(bool(report))
        if report:
            self.results_controller.refresh_results(report)
        self._refresh_results_tables()

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
        self.parallel_spin.setValue(defaults.parallel_downloads)
        self.mark_dirty()
        self.statusBar().showMessage(
            translate_text("Valores recomendados restaurados. Salve o projeto."),
            4000,
        )

    def _refresh_dashboard(self) -> None:
        self._refresh_home()
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
        ready = {
            "source": source is not None,
            "connection": source is not None and self._credentials_available(source),
            "selection": bool(selected),
            "format": True,
            "consolidation": True,
        }
        for key, icon in getattr(self, "review_status_icons", {}).items():
            icon.setText("✓" if ready[key] else "⚠")
        estimate = len(self.last_consolidation_preview)
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
    from PySide6.QtCore import QSettings

    from .i18n import settings_path

    # The interface scale must be set before the QApplication exists.
    scale: Any = QSettings(str(settings_path()), QSettings.Format.IniFormat).value("preferences/ui_scale", 1.0)
    try:
        if float(scale or 1.0) != 1.0:
            os.environ["QT_SCALE_FACTOR"] = str(float(scale))
    except (TypeError, ValueError):
        pass
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("ALQuimista Studio")
    app.setOrganizationName("ALQuimista")
    from .i18n import initialize_language

    language_manager = initialize_language(app)
    window = MainWindow(mode, language_manager)
    window.show()
    QTimer.singleShot(0, window.reopen_last_project)
    QTimer.singleShot(400, window.offer_tour_once)
    raise SystemExit(app.exec())


__all__ = ["MainWindow", "run_app"]
