from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QStackedWidget, QWidget

from ..i18n import LanguageManager, retranslate_widget_tree, translate_text


class NavigationController:
    """Orchestrates page routing, navigation sidebar state, and UI retranslation."""

    def __init__(
        self,
        stack: QStackedWidget,
        nav_buttons: dict[str, QPushButton],
        pages: dict[str, QWidget],
        i18n: LanguageManager,
        on_page_changed: Callable[[str], None] | None = None,
        op_mode_combo: QComboBox | None = None,
        op_mode_help_label: QLabel | None = None,
    ) -> None:
        self.stack = stack
        self.nav_buttons = nav_buttons
        self.pages = pages
        self.i18n = i18n
        self.on_page_changed = on_page_changed
        self.op_mode_combo = op_mode_combo
        self.op_mode_help_label = op_mode_help_label

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if not page:
            return
        self.stack.setCurrentWidget(page)
        for name, nav in self.nav_buttons.items():
            nav.setChecked(name == key)
        if self.on_page_changed is not None:
            self.on_page_changed(key)

    def update_execution_mode_help(self) -> None:
        if self.op_mode_help_label is None or self.op_mode_combo is None:
            return
        choice = self.op_mode_combo.currentData() or "complete"
        if choice == "extractor":
            self.op_mode_help_label.setText(
                translate_text(
                    "Modo Extrator: executa a descoberta, download e conversão para Markdown individual por documento, gerando o manifesto incremental."
                )
            )
        elif choice == "consolidator":
            self.op_mode_help_label.setText(
                translate_text(
                    "Modo Consolidador: lê os documentos previamente extraídos e gera o pacote consolidado em arquivo único com índice e separadores estruturados."
                )
            )
        else:
            self.op_mode_help_label.setText(
                translate_text(
                    "Fluxo Completo: extrai o conteúdo atualizado das fontes ativas e em seguida gera a consolidação estruturada com base nas opções configuradas."
                )
            )

    def language_changed(
        self,
        _language: str,
        *,
        window: QWidget,
        language_combo: QComboBox | None = None,
        on_retranslate_callbacks: list[Callable[[], None]] | None = None,
    ) -> None:
        self.retranslate_ui(
            window,
            language_combo=language_combo,
            callbacks=on_retranslate_callbacks,
        )

    def retranslate_ui(
        self,
        window: QWidget,
        *,
        language_combo: QComboBox | None = None,
        callbacks: list[Callable[[], None]] | None = None,
    ) -> None:
        """Refresh visible UI labels while keeping language combo data stable."""
        excluded = (language_combo,) if language_combo is not None else ()
        retranslate_widget_tree(window, exclude=excluded)
        if language_combo is not None:
            selected = self.i18n.language
            index = language_combo.findData(selected)
            if index >= 0 and language_combo.currentIndex() != index:
                blocker = QSignalBlocker(language_combo)
                language_combo.setCurrentIndex(index)
                del blocker
        self.update_execution_mode_help()
        for callback in callbacks or []:
            callback()

    def change_language(self, language: str) -> None:
        self.i18n.set_language(language)


__all__ = ["NavigationController"]
