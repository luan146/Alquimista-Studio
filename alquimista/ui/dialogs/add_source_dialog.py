"""'Adicionar fonte': paste a URL (or pick a file/folder) or start from the platform catalog."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ..components import button
from ..i18n import translate_text
from ..pages.source_catalog import build_source_catalog


class AddSourceDialog(QDialog):
    """Owns the visible source form; the logic stays in ``SourceMixin``.

    The widgets are published on the window (``source_url_input``,
    ``source_add_button``...) so existing handlers keep working unchanged.
    """

    def __init__(self, window: Any) -> None:
        super().__init__(window)
        self.window_ref = window
        self.setWindowTitle(translate_text("Adicionar fonte"))
        self.resize(980, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        title = QLabel("Cole a URL da fonte")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        hint = QLabel(
            "Página, espaço, site ou raiz da plataforma: o ALQuimista identifica a plataforma "
            "e a API pela URL. Para arquivos do computador, use Arquivo ou Pasta."
        )
        hint.setObjectName("subtitle")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        url_row = QHBoxLayout()
        window.source_url_input = QLineEdit()
        window.source_url_input.setPlaceholderText(
            "Cole aqui a URL do Confluence, Notion, SharePoint, GitBook ou Zendesk"
        )
        window.source_url_input.setAccessibleName("URL da fonte")
        window.source_url_input.setMinimumHeight(38)
        window.source_url_input.textChanged.connect(window._preview_detected_source)
        window.source_url_input.returnPressed.connect(self._commit)
        url_row.addWidget(window.source_url_input, 1)
        url_row.addWidget(button("📁 Arquivo...", window._pick_local_file))
        url_row.addWidget(button("📂 Pasta...", window._pick_local_folder))
        layout.addLayout(url_row)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Nome da fonte (opcional)"))
        window.source_name_input = QLineEdit()
        window.source_name_input.setPlaceholderText("Nome da fonte")
        window.source_name_input.setAccessibleName("Nome opcional da fonte")
        window.source_name_input.returnPressed.connect(self._commit)
        name_row.addWidget(window.source_name_input, 1)
        layout.addLayout(name_row)

        window.source_detection_status = QLabel(
            "A plataforma, a API e os detalhes iniciais serão identificados pela URL."
        )
        window.source_detection_status.setObjectName("subtitle")
        window.source_detection_status.setWordWrap(True)
        layout.addWidget(window.source_detection_status)

        actions = QHBoxLayout()
        actions.addStretch()
        window.source_cancel_button = button("Cancelar", self.reject)
        window.source_add_button = button("＋ Adicionar", self._commit, primary=True)
        actions.addWidget(window.source_cancel_button)
        actions.addWidget(window.source_add_button)
        layout.addLayout(actions)

        catalog_title = QLabel("Ou escolha a plataforma")
        catalog_title.setStyleSheet("font-size: 12pt; font-weight: 700;")
        layout.addWidget(catalog_title)
        layout.addWidget(build_source_catalog(window), 1)

    def _commit(self) -> None:
        if self.window_ref._commit_source_from_form():
            self.accept()

    def reject(self) -> None:
        self.window_ref._reset_source_form()
        super().reject()

    def open_for_add(self) -> None:
        self.window_ref._reset_source_form()
        self.setWindowTitle(translate_text("Adicionar fonte"))
        self.window_ref.source_url_input.setFocus()
        self.open()

    def open_for_edit(self) -> None:
        """The form was already filled by ``_edit_source_row``."""
        self.setWindowTitle(translate_text("Editar fonte"))
        self.window_ref.source_url_input.setFocus()
        self.open()
