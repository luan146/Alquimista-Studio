"""Internationalization and user preferences for ALQuimista Studio."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLocale, QObject, QSettings, QTranslator, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from .translation_fallbacks import supplemental_translation

SUPPORTED_LANGUAGES = ("pt-BR", "en", "es")
LANGUAGE_NAMES = {
    "pt-BR": "Português (Brasil)",
    "en": "English",
    "es": "Español",
}
_LANGUAGE_ALIASES = {
    "pt": "pt-BR",
    "pt_br": "pt-BR",
    "pt-br": "pt-BR",
    "en-gb": "en",
    "en_us": "en",
    "es_es": "es",
    "es-es": "es",
}


def normalize_language(value: str | None) -> str | None:
    """Return a supported language code, or ``None`` for automatic detection."""
    if value is None:
        return None
    normalized = value.strip().replace("_", "-").lower()
    if normalized in {"", "system", "auto"}:
        return None
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    if normalized.startswith("pt-"):
        return "pt-BR"
    if normalized.startswith("en-"):
        return "en"
    if normalized.startswith("es-"):
        return "es"
    if normalized in {language.lower() for language in SUPPORTED_LANGUAGES}:
        return normalized if normalized != "pt-br" else "pt-BR"
    return None


def system_language() -> str:
    language = normalize_language(QLocale.system().name())
    return language or "pt-BR"


def portable_root() -> Path:
    """Return the directory used to detect portable distributions."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def is_portable() -> bool:
    explicit = os.environ.get("ALQUIMISTA_PORTABLE", "").strip().lower()
    return explicit in {"1", "true", "yes"} or (portable_root() / "portable.flag").exists()


def settings_directory() -> Path:
    if is_portable():
        return portable_root() / "data"
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "ALQuimista Studio"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "alquimista-studio"


def settings_path() -> Path:
    return settings_directory() / "settings.ini"


def create_settings() -> QSettings:
    """Create file-backed settings for both portable and installed builds."""
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        settings = QSettings(str(path), QSettings.Format.IniFormat)
        if not path.exists() and not is_portable():
            legacy = QSettings("ALQuimista Studio", "ALQuimista Studio")
            for key in legacy.allKeys():
                settings.setValue(key, legacy.value(key))
            settings.sync()
        return settings
    except OSError:
        # A read-only portable folder must remain usable. QSettings' native
        # fallback keeps the UI functional without moving project data.
        return QSettings("ALQuimista", "ALQuimista Studio")


class LanguageManager(QObject):
    """Own the active Qt translator and the persisted language preference."""

    language_changed = Signal(str)

    def __init__(self, app: QCoreApplication, settings: QSettings | None = None) -> None:
        super().__init__()
        self.app = app
        self.settings = settings or create_settings()
        self.translator = QTranslator(app)
        self.language = "pt-BR"

    @property
    def preferred_language(self) -> str | None:
        return normalize_language(self.settings.value("preferences/language"))

    def choose_initial_language(self) -> str:
        preferred = self.preferred_language
        if preferred:
            return preferred
        return system_language()

    def set_language(self, language: str, *, persist: bool = True) -> str:
        selected = normalize_language(language) or "pt-BR"
        previous = self.app.property("_alquimista_translator")
        if previous is not None and previous is not self.translator:
            self.app.removeTranslator(previous)
        if self.translator is not None:
            self.app.removeTranslator(self.translator)
        self.translator = QTranslator(self.app)
        if selected != "pt-BR":
            resource = Path(__file__).with_name("translations") / f"ALQuimista_{selected}.qm"
            self.translator.load(str(resource))
            self.app.installTranslator(self.translator)
            self.app.setProperty("_alquimista_translator", self.translator)
        else:
            self.app.setProperty("_alquimista_translator", None)
        self.language = selected
        self.app.setProperty("_alquimista_language", selected)
        if persist:
            self.settings.setValue("preferences/language", selected)
            self.settings.sync()
        self.language_changed.emit(selected)
        return selected

    def translate(self, source: str, disambiguation: str | None = None) -> str:
        if self.language == "pt-BR":
            return source
        translated = QCoreApplication.translate("ALQuimista", source, disambiguation)
        return supplemental_translation(source, self.language) or translated


def translate_text(source: str) -> str:
    """Translate a UI string through the current application translator."""
    translated = QCoreApplication.translate("ALQuimista", source)
    app = QCoreApplication.instance()
    language = str(app.property("_alquimista_language") or "pt-BR") if app else "pt-BR"
    if language == "pt-BR":
        return source
    return supplemental_translation(source, language) or translated


def _remember(widget: QWidget, key: str, value: str) -> str:
    property_name = f"_alquimista_{key}"
    original = widget.property(property_name)
    if original is None:
        widget.setProperty(property_name, value)
        return value
    return str(original)


def retranslate_widget_tree(root: QWidget, *, exclude: tuple[QWidget, ...] = ()) -> None:
    """Refresh static widget properties without changing internal item data."""
    excluded = set(exclude)
    for widget in [root, *root.findChildren(QWidget)]:
        if widget in excluded or any(item.isAncestorOf(widget) for item in excluded):
            continue
        if isinstance(widget, QComboBox):
            for index in range(widget.count()):
                source = _remember(widget, f"item_{index}", widget.itemText(index))
                widget.setItemText(index, translate_text(source))
        elif isinstance(widget, QTableWidget):
            for index in range(widget.columnCount()):
                item = widget.horizontalHeaderItem(index)
                if item is not None:
                    source = item.data(0x0100) or item.text()
                    item.setData(0x0100, source)
                    item.setText(translate_text(str(source)))
        elif isinstance(widget, QTreeWidget):
            header = widget.headerItem()
            if header is not None:
                for index in range(widget.columnCount()):
                    source = header.data(index, 0x0100) or header.text(index)
                    header.setData(index, 0x0100, source)
                    header.setText(index, translate_text(str(source)))

        text_getter = getattr(widget, "text", None)
        text_setter = getattr(widget, "setText", None)
        if callable(text_getter) and callable(text_setter):
            value = text_getter()
            if value:
                source = _remember(widget, "text", str(value))
                text_setter(translate_text(source))
        placeholder_getter = getattr(widget, "placeholderText", None)
        placeholder_setter = getattr(widget, "setPlaceholderText", None)
        if callable(placeholder_getter) and callable(placeholder_setter):
            placeholder = placeholder_getter()
            if placeholder:
                source = _remember(widget, "placeholder", str(placeholder))
                placeholder_setter(translate_text(source))
        for key, value, setter in (
            ("tooltip", widget.toolTip(), widget.setToolTip),
            ("accessible", widget.accessibleName(), widget.setAccessibleName),
            ("window_title", widget.windowTitle(), widget.setWindowTitle),
        ):
            if value:
                source = _remember(widget, key, value)
                setter(translate_text(source))


class LanguageDialog(QDialog):
    """Small first-run language picker shown before the main window."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        language = system_language()
        labels = {
            "pt-BR": ("Escolha o idioma da interface", "Escolha o idioma do ALQuimista Studio:"),
            "en": ("Choose interface language", "Choose the language for ALQuimista Studio:"),
            "es": ("Elige el idioma de la interfaz", "Elige el idioma de ALQuimista Studio:"),
        }
        title, prompt = labels[language]
        self.setWindowTitle(title)
        self.selected_language = "pt-BR"
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))
        self.combo = QComboBox()
        for code in SUPPORTED_LANGUAGES:
            self.combo.addItem(LANGUAGE_NAMES[code], code)
        layout.addWidget(self.combo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        self.selected_language = str(self.combo.currentData())
        super().accept()


def initialize_language(app: QCoreApplication) -> LanguageManager:
    manager = LanguageManager(app)
    initial = manager.preferred_language
    if initial is None:
        # The dialog uses native language names and therefore works before a
        # translator has been installed.
        dialog = LanguageDialog()
        if dialog.exec() == QDialog.DialogCode.Accepted:
            initial = dialog.selected_language
        else:
            initial = manager.choose_initial_language()
    manager.set_language(initial)
    return manager
