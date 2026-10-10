"""Comfort features: preferences, banners, collapsible sidebar, drag and drop,
real-page preview, guided tour and the sample project."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ...connectors.local_files import LocalFilesConnector
from ...models import KnowledgeSelection, SourceConfig, default_project
from ...runtime import CancellationToken
from ...services.extraction import ExtractionService
from ..components import NAVIGATION
from ..i18n import translate_text
from ..theme import apply_theme
from . import WindowBase

# Below this window width the sidebar shows icons only (unless the user chose).
COMPACT_WIDTH = 1200
EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "assets" / "exemplo"
TOUR_STEPS = [
    ("dashboard", "Início", "Aqui você vê a situação do projeto, o próximo passo e os projetos recentes."),
    ("sources", "1. Fontes", "Adicione fontes colando a URL (ou arrastando para a janela) e conecte cada uma: "
     "token ou login pelo navegador."),
    ("selection", "2. Seleção", "Marque espaços inteiros na tabela ou abra um espaço para escolher páginas. "
     "Clique duas vezes numa página para ver o Markdown dela."),
    ("format", "3. Saída", "Ajuste o que entra em cada Markdown e como os pacotes para IA são montados."),
    ("extraction", "4. Executar", "Confira o checklist, escolha a pasta e execute (F5). Cancelar não perde o que já foi feito."),
    ("results", "5. Resultados", "Veja falhas com ações, o histórico de execuções e abra a pasta gerada."),
]


class UxMixin(WindowBase):
    project: Any
    project_path: Path | None
    ui_settings: Any
    secrets: Any
    connector_registry: Any
    worker: Any
    sidebar: Any
    sidebar_toggle: Any
    sidebar_texts: list[Any]
    nav_buttons: dict[str, Any]
    nav_status: dict[str, Any]
    banner: Any
    banner_label: Any
    banner_action: Any
    preview_controller: Any
    preview_source_label: Any
    preview_sample_button: Any
    source_url_input: Any
    source_name_input: Any
    trees: Any
    selection_store: Any
    _show_page: Any
    _start_worker: Any
    _update_preview: Any
    _commit_source_from_form: Any
    _confirm_discard: Any
    _load_project_ui: Any
    _refresh_workflow_state: Any

    # --- preferences -------------------------------------------------------

    def _theme_preference(self) -> str:
        return str(self.ui_settings.value("preferences/theme", "system") or "system")

    def _set_theme(self, value: str) -> None:
        self.ui_settings.setValue("preferences/theme", value)
        self.ui_settings.sync()
        apply_theme(QApplication.instance(), value)

    def _ui_scale_preference(self) -> float:
        try:
            return float(self.ui_settings.value("preferences/ui_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            return 1.0

    def _set_ui_scale(self, value: float) -> None:
        self.ui_settings.setValue("preferences/ui_scale", value)
        self.ui_settings.sync()
        self.notify(translate_text("O novo tamanho da interface vale ao reabrir o programa."))

    # --- banners -------------------------------------------------------------

    def notify(
        self,
        message: str,
        kind: str = "info",
        *,
        action: tuple[str, Callable[[], object]] | None = None,
        timeout_ms: int = 8000,
    ) -> None:
        """Non-blocking message at the top of the window (replaces informational pop-ups)."""
        if not hasattr(self, "banner"):
            return
        self.banner.setProperty("kind", kind)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner_label.setText(message)
        self.banner_action.setVisible(action is not None)
        self._banner_callback = action[1] if action else None
        if action is not None:
            self.banner_action.setText(action[0])
        self.banner.show()
        timer = getattr(self, "_banner_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.banner.hide)
            self._banner_timer = timer
        timer.start(timeout_ms)

    def _banner_action_clicked(self) -> None:
        self.banner.hide()
        callback = getattr(self, "_banner_callback", None)
        if callback is not None:
            callback()

    # --- sidebar -------------------------------------------------------------

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(72 if collapsed else 235)
        labels = dict(NAVIGATION)
        for key, nav in self.nav_buttons.items():
            nav.setText("" if collapsed else translate_text(labels[key]))
            nav.setToolTip(translate_text(labels[key]))
            status = self.nav_status.get(key)
            if status is not None:
                status.setVisible(not collapsed)
        for widget in self.sidebar_texts:
            widget.setVisible(not collapsed)
        self.sidebar_toggle.setText("»" if collapsed else "«")
        self.sidebar_toggle.setToolTip(
            translate_text("Mostrar nomes das etapas") if collapsed else translate_text("Recolher barra lateral")
        )

    def _toggle_sidebar(self) -> None:
        # A manual choice wins over the automatic width rule from now on.
        self._sidebar_manual = True
        self._set_sidebar_collapsed(not getattr(self, "_sidebar_collapsed", False))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        compact = event.size().width() < COMPACT_WIDTH
        if hasattr(self, "source_table"):
            # Narrow windows: the URL stays available as the name's tooltip.
            self.source_table.setColumnHidden(2, compact)
        if hasattr(self, "sidebar") and not getattr(self, "_sidebar_manual", False):
            if compact != getattr(self, "_sidebar_collapsed", False):
                self._set_sidebar_collapsed(compact)

    # --- drag and drop -------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls() or mime.hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        """A URL, file or folder dropped anywhere on the window becomes a source."""
        mime = event.mimeData()
        values = [
            url.toLocalFile() if url.isLocalFile() else url.toString() for url in mime.urls()
        ] or [line.strip() for line in mime.text().splitlines() if line.strip()]
        added = 0
        for value in values:
            self.source_url_input.setText(value)
            self.source_name_input.clear()
            added += bool(self._commit_source_from_form())
        event.acceptProposedAction()
        if added:
            self._show_page("sources")
            self.notify(translate_text("{count} fonte(s) adicionada(s). Agora conecte cada uma.").format(count=added), "success")

    # --- real-page preview -----------------------------------------------------

    def _preview_real_page(self, source: SourceConfig, container_id: str, document_id: str, title: str) -> None:
        if self.worker is not None:
            self.notify(translate_text("Aguarde a operação atual terminar…"), "warning")
            return
        project = self.project

        def work(token: CancellationToken, progress: Any, log: Any) -> Any:
            progress(0, 1, translate_text("Buscando a página {title}").format(title=title))
            connector = self.connector_registry.create(
                source,
                options=project.extraction,
                markdown_options=project.markdown,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            )
            try:
                return ExtractionService._fetch_document(connector, document_id, container_id)
            finally:
                connector.close()

        def done(document: Any) -> None:
            self.preview_controller.real_document = (document, source)
            self._show_page("markdown")
            self._update_preview()
            self._show_preview_source(title)

        self._start_worker(work, done)

    def _show_preview_source(self, title: str | None) -> None:
        if title:
            self.preview_source_label.setText(
                translate_text("Página real: “{title}”. As opções ao lado são aplicadas a ela.").format(title=title)
            )
        else:
            self.preview_source_label.setText(
                translate_text("Página de exemplo. Para ver uma página sua, clique duas vezes nela em Seleção.")
            )
        self.preview_sample_button.setVisible(bool(title))

    def _clear_real_preview(self) -> None:
        self.preview_controller.real_document = None
        self._update_preview()
        self._show_preview_source(None)

    # --- sample project and tour ---------------------------------------------

    def open_example_project(self) -> None:
        """A local-folder project with every page selected: try the flow without credentials."""
        if not self._confirm_discard():
            return
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".alquimista-studio") / "ALQuimista Studio" / "Exemplo"
        documents = root / "documentos"
        # Copy so the bundled files stay untouched and the output has a writable home.
        shutil.copytree(EXAMPLE_DIR, documents, dirs_exist_ok=True)
        source = SourceConfig(
            id="exemplo",
            name=translate_text("Base de exemplo"),
            source_type="local_files",
            base_url=str(documents),
            connector_options={"path": str(documents), "source_url": str(documents)},
        )
        connector = LocalFilesConnector(source, default_project().extraction)
        selections = [
            KnowledgeSelection(source_id=source.id, container_id=container.id, document_id=document.id)
            for container in connector.list_containers()
            for document in connector.list_documents(container.id)
        ]
        project = default_project()
        project.project_name = translate_text("Projeto de exemplo")
        project.sources = [source]
        project.selections = selections
        project.output_dir = str(root / "saida")
        self.project = project
        self.project_path = None
        self.trees.clear()
        self.secrets.clear()
        self._load_project_ui()
        self.dirty = False
        self._show_page("dashboard")
        self.notify(
            translate_text("Projeto de exemplo pronto: {count} documentos já selecionados. Vá em Executar (F5).").format(
                count=len(selections)
            ),
            "success",
            action=(translate_text("Ir para Executar"), lambda: self._show_page("extraction")),
            timeout_ms=15000,
        )

    def start_tour(self) -> None:
        TourDialog(self).show()

    def offer_tour_once(self) -> None:
        """First start: show the tour once (it can be reopened from Configurações)."""
        if self.ui_settings.value("preferences/tour_seen", False) in (True, "true"):
            return
        self.ui_settings.setValue("preferences/tour_seen", True)
        self.ui_settings.sync()
        self.start_tour()


class TourDialog(QDialog):
    """Five short steps; each one opens the matching page behind the dialog."""

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window_ref = window
        self.index = 0
        self.setWindowTitle(translate_text("Tour guiado"))
        self.setModal(False)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(self.title)
        self.text = QLabel()
        self.text.setWordWrap(True)
        layout.addWidget(self.text)
        self.counter = QLabel()
        self.counter.setObjectName("subtitle")
        layout.addWidget(self.counter)
        buttons = QHBoxLayout()
        self.example_button = QPushButton(translate_text("🧪 Experimentar com um exemplo"))
        self.example_button.clicked.connect(self._example)
        buttons.addWidget(self.example_button)
        buttons.addStretch()
        skip = QPushButton(translate_text("Pular"))
        skip.clicked.connect(self.close)
        buttons.addWidget(skip)
        self.back = QPushButton(translate_text("Anterior"))
        self.back.clicked.connect(lambda: self._go(-1))
        buttons.addWidget(self.back)
        self.next = QPushButton()
        self.next.setDefault(True)
        self.next.clicked.connect(lambda: self._go(1))
        buttons.addWidget(self.next)
        layout.addLayout(buttons)
        self._render()

    def _go(self, step: int) -> None:
        if self.index + step >= len(TOUR_STEPS):
            self.close()
            return
        self.index = max(0, self.index + step)
        self._render()

    def _render(self) -> None:
        key, title, text = TOUR_STEPS[self.index]
        self.window_ref._show_page(key)
        self.title.setText(translate_text(title))
        self.text.setText(translate_text(text))
        self.counter.setText(f"{self.index + 1}/{len(TOUR_STEPS)}")
        self.back.setEnabled(self.index > 0)
        self.example_button.setVisible(self.index == 0)
        last = self.index == len(TOUR_STEPS) - 1
        self.next.setText(translate_text("Concluir") if last else translate_text("Próximo →"))
        # Keep the dialog in the lower-right corner, out of the page's way.
        parent = self.window_ref.geometry()
        self.adjustSize()
        self.move(parent.right() - self.width() - 40, parent.bottom() - self.height() - 90)

    def _example(self) -> None:
        self.close()
        self.window_ref.open_example_project()

