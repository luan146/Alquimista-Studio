"""Theme tokens (light/dark) and the application stylesheet."""
from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .icons import ICON_DIR

LIGHT = {
    "window": "#F7F7F5", "surface": "#FFFFFF", "surface_alt": "#EFEEEA", "text": "#37352F",
    "muted": "#787774", "border": "#E9E9E7", "primary": "#0F9E8A", "primary_hover": "#0C8574",
    "primary_soft": "#E3F2EF", "on_primary": "#FFFFFF", "success": "#15803D", "success_soft": "#DCFCE7",
    "warning": "#B45309", "warning_soft": "#FEF3C7", "danger": "#B91C1C", "danger_soft": "#FEE2E2",
    "accent": "#6D28D9",
}
DARK = {
    "window": "#191919", "surface": "#252525", "surface_alt": "#2F2F2F", "text": "#E9E9E7",
    "muted": "#9B9A97", "border": "#373737", "primary": "#2DD4BF", "primary_hover": "#5EEAD4",
    "primary_soft": "#16302B", "on_primary": "#04342C", "success": "#4ADE80", "success_soft": "#14532D",
    "warning": "#FBBF24", "warning_soft": "#713F12", "danger": "#F87171", "danger_soft": "#7F1D1D",
    "accent": "#A78BFA",
}
_current: dict[str, str] = LIGHT


def current_colors() -> dict[str, str]:
    """Colors of the theme applied last; custom painters read them so a theme switch shows at once."""
    return _current


def is_dark() -> bool:
    return _current is DARK


def _image(name: str) -> str:
    return f'url("{(ICON_DIR / f"{name}.svg").as_posix()}")'


def stylesheet(c: dict[str, str]) -> str:
    return f"""
    * {{ font-family: "Segoe UI", "Segoe UI Emoji"; font-size: 10pt; color: {c["text"]}; }}
    QMainWindow, QWidget#root, QDialog {{ background: {c["window"]}; }}
    QFrame#sidebar {{ background: {c["window"]}; border: 0; border-right: 1px solid {c["border"]}; }}
    QFrame#topBar {{ background: {c["window"]}; border: 0; border-bottom: 1px solid {c["border"]}; }}
    QFrame#stepFooter {{ background: {c["window"]}; border: 0; border-top: 1px solid {c["border"]}; }}
    QLabel#brand {{ font-size: 14pt; font-weight: 700; }}
    QLabel#pageTitle {{ font-size: 18pt; font-weight: 600; }}
    QLabel#sectionTitle {{ font-size: 11.5pt; font-weight: 600; }}
    QLabel#subtitle, QLabel[muted="true"], QLabel#navStepStatus {{ color: {c["muted"]}; }}
    QLabel#runCount {{ font-size: 22pt; font-weight: 600; }}
    QLabel#optionTitle {{ font-weight: 600; }}
    QFrame#card, QGroupBox, QFrame#connectionPanel, QFrame#markdownPreviewCard,
    QFrame#consolidationControlsCard, QFrame#consolidationPreviewCard, QFrame#pageTableCard,
    QFrame#sourcePanel, QFrame#accountCard, QFrame#metricCard, QFrame#statCard {{
        background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 12px; }}
    QFrame#markdownSection, QFrame#consolidationStep, QFrame#consolidationMetric, QFrame#pageStat,
    QFrame#consolidationSummary {{
        background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 10px; }}
    QFrame#pageSummaryCard, QFrame#optionRow {{ background: transparent; border: 0; }}
    QFrame#optionRow {{ border-bottom: 1px solid {c["border"]}; }}
    QGroupBox {{ margin-top: 12px; padding: 18px 12px 12px 12px; font-weight: 600; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}

    QPushButton {{ background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 9px; padding: 7px 14px; }}
    QPushButton:hover {{ background: {c["surface_alt"]}; }}
    QPushButton:pressed {{ background: {c["border"]}; }}
    QPushButton:focus {{ border-color: {c["primary"]}; }}
    QPushButton[primary="true"] {{ background: {c["primary"]}; color: {c["on_primary"]}; border-color: {c["primary"]}; font-weight: 600; }}
    QPushButton[primary="true"]:hover {{ background: {c["primary_hover"]}; border-color: {c["primary_hover"]}; }}
    QPushButton[danger="true"] {{ color: {c["danger"]}; }}
    QPushButton[danger="true"]:hover {{ background: {c["danger_soft"]}; border-color: {c["danger_soft"]}; }}
    QPushButton[ghost="true"] {{ background: transparent; border-color: transparent; color: {c["muted"]}; }}
    QPushButton[ghost="true"]:hover {{ background: {c["surface_alt"]}; color: {c["text"]}; }}
    QPushButton[ghost="true"][danger="true"] {{ color: {c["danger"]}; }}
    QPushButton[ghost="true"][danger="true"]:hover {{ background: {c["danger_soft"]}; color: {c["danger"]}; }}
    QPushButton[ghost="true"]:focus {{ border-color: {c["primary"]}; }}
    QPushButton:disabled {{ color: {c["muted"]}; background: {c["surface_alt"]}; border-color: {c["border"]}; }}
    QPushButton#googleButton {{ border-radius: 22px; padding: 10px 18px; font-size: 10.5pt; font-weight: 600; }}
    QPushButton#googleButton:hover {{ border-color: {c["muted"]}; }}
    QPushButton#navButton {{ text-align: left; border: 0; border-radius: 9px; padding: 9px 12px; background: transparent; color: {c["muted"]}; }}
    QPushButton#navButton:hover {{ background: {c["surface_alt"]}; color: {c["text"]}; }}
    QPushButton#navButton:checked {{ background: {c["primary_soft"]}; color: {c["primary"]}; font-weight: 600; }}
    QPushButton#categoryPill {{ border-radius: 13px; padding: 4px 12px; font-size: 9pt; }}
    QPushButton#categoryPill:checked {{ background: {c["primary"]}; color: {c["on_primary"]}; border-color: {c["primary"]}; }}
    QPushButton#markdownSectionHeader {{ text-align: left; border: 0; padding: 10px 12px; background: transparent; font-weight: 600; }}
    QPushButton#markdownTextButton {{ border: 0; padding: 4px 6px; background: transparent; color: {c["primary"]}; }}
    QToolButton {{ border: 0; border-radius: 8px; padding: 4px 8px; background: transparent; }}
    QToolButton:hover {{ background: {c["surface_alt"]}; }}
    QToolButton::menu-indicator {{ image: none; }}
    QToolButton#presetCard {{ background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 12px; padding: 10px; }}
    QToolButton#presetCard:checked {{ border: 2px solid {c["primary"]}; }}

    QFrame#segmented {{ background: {c["surface_alt"]}; border: 0; border-radius: 12px; }}
    QFrame#segmented QPushButton {{ background: transparent; border: 1px solid transparent; border-radius: 9px; padding: 5px 14px; color: {c["muted"]}; }}
    QFrame#segmented QPushButton:hover {{ color: {c["text"]}; }}
    QFrame#segmented QPushButton:checked {{ background: {c["surface"]}; color: {c["text"]}; font-weight: 600; }}
    QFrame#segmented[vertical="true"] {{ background: transparent; }}
    QFrame#segmented[vertical="true"] QPushButton {{ text-align: left; padding: 8px 12px; }}
    QFrame#segmented[vertical="true"] QPushButton:checked {{ background: {c["primary_soft"]}; color: {c["primary"]}; }}
    QFrame#segmented[tiles="true"] {{ background: transparent; }}
    QFrame#segmented[tiles="true"] QToolButton {{ background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 12px; padding: 8px; }}
    QFrame#segmented[tiles="true"] QToolButton:checked {{ border: 2px solid {c["primary"]}; }}
    QFrame#segmented QPushButton:focus {{ border-color: {c["primary"]}; }}
    QFrame#segmented[tiles="true"] QToolButton:focus {{ border-color: {c["primary"]}; background: {c["primary_soft"]}; }}

    QLabel#chip {{ border-radius: 10px; padding: 2px 10px; font-size: 9pt; font-weight: 600; background: {c["surface_alt"]}; color: {c["muted"]}; }}
    QLabel#chip[kind="accent"] {{ background: {c["primary_soft"]}; color: {c["primary"]}; }}
    QLabel#chip[kind="success"] {{ background: {c["success_soft"]}; color: {c["success"]}; }}
    QLabel#chip[kind="warning"] {{ background: {c["warning_soft"]}; color: {c["warning"]}; }}
    QLabel#chip[kind="danger"] {{ background: {c["danger_soft"]}; color: {c["danger"]}; }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QTextEdit, QPlainTextEdit {{
        background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 9px; padding: 6px 9px;
        selection-background-color: {c["primary"]}; selection-color: {c["on_primary"]}; }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTimeEdit:focus, QTextEdit:focus {{ border-color: {c["primary"]}; }}
    QLineEdit#searchField {{ border-radius: 16px; padding-left: 12px; background: {c["surface_alt"]}; border-color: {c["surface_alt"]}; }}
    QLineEdit#searchField:focus {{ border-color: {c["primary"]}; background: {c["surface"]}; }}
    QComboBox::drop-down {{ border: 0; width: 26px; }}
    QComboBox::down-arrow {{ image: {_image("controle_seta_baixo")}; width: 12px; height: 12px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 20px;
        background: transparent; border: 0; }}
    QAbstractSpinBox::up-button {{ subcontrol-position: top right; }}
    QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; }}
    QAbstractSpinBox::up-arrow {{ image: {_image("controle_seta_cima")}; width: 10px; height: 10px; }}
    QAbstractSpinBox::down-arrow {{ image: {_image("controle_seta_baixo")}; width: 10px; height: 10px; }}
    QComboBox QAbstractItemView {{ background: {c["surface"]}; border: 1px solid {c["border"]}; outline: 0;
        selection-background-color: {c["primary_soft"]}; selection-color: {c["text"]}; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator, QTreeView::indicator, QListView::indicator, QTableView::indicator {{ width: 18px; height: 18px; }}
    QCheckBox::indicator:unchecked, QTreeView::indicator:unchecked, QListView::indicator:unchecked,
    QTableView::indicator:unchecked {{ image: {_image("controle_check_off")}; }}
    QCheckBox::indicator:checked, QTreeView::indicator:checked, QListView::indicator:checked,
    QTableView::indicator:checked {{ image: {_image("controle_check_on")}; }}
    QCheckBox::indicator:indeterminate, QTreeView::indicator:indeterminate,
    QTableView::indicator:indeterminate {{ image: {_image("controle_check_partial")}; }}
    QCheckBox[switch="true"]::indicator {{ width: 36px; height: 20px; border: 2px solid transparent; border-radius: 12px; }}
    QCheckBox[switch="true"]::indicator:unchecked {{ image: {_image("controle_switch_off")}; }}
    QCheckBox[switch="true"]::indicator:checked {{ image: {_image("controle_switch_on")}; }}
    QCheckBox[switch="true"]:focus {{ color: {c["primary"]}; }}
    QCheckBox[switch="true"]::indicator:focus {{ border-color: {c["primary"]}; }}

    QTreeView, QTreeWidget, QTableWidget, QTableView, QListWidget {{
        background: {c["surface"]}; alternate-background-color: {c["surface"]};
        border: 1px solid {c["border"]}; border-radius: 12px; outline: 0; padding: 4px; }}
    QTreeView::item, QTableView::item, QListView::item {{ padding: 6px 4px; border: 0; }}
    QTreeView::item:hover, QTableView::item:hover, QListView::item:hover {{ background: {c["surface_alt"]}; }}
    QTreeView::item:selected, QTableView::item:selected, QListView::item:selected {{ background: {c["primary_soft"]}; color: {c["text"]}; }}
    QListWidget#spaceCards {{ background: transparent; border: 0; padding: 0; }}
    QListWidget#spaceCards::item, QListWidget#spaceCards::item:hover, QListWidget#spaceCards::item:selected {{ background: transparent; }}
    QHeaderView::section {{ background: {c["surface"]}; color: {c["muted"]}; border: 0; border-bottom: 1px solid {c["border"]};
        padding: 8px 6px; font-weight: 600; font-size: 9pt; }}
    QProgressBar {{ border: 0; background: {c["surface_alt"]}; border-radius: 6px; min-height: 12px; max-height: 12px;
        text-align: center; font-size: 8pt; }}
    QProgressBar::chunk {{ background: {c["primary"]}; border-radius: 6px; }}
    QTabWidget::pane {{ border: 0; }}
    QTabBar::tab {{ background: transparent; border: 1px solid transparent; padding: 7px 14px; margin-right: 4px;
        border-radius: 9px; color: {c["muted"]}; }}
    QTabBar::tab:selected {{ background: {c["surface"]}; border-color: {c["border"]}; color: {c["text"]}; font-weight: 600; }}
    QTabBar::tab:hover:!selected {{ color: {c["text"]}; }}
    QScrollArea {{ border: 0; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {c["border"]}; border-radius: 4px; min-height: 30px; min-width: 30px; }}
    QScrollBar::handle:hover {{ background: {c["muted"]}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolTip {{ background: {c["surface"]}; color: {c["text"]}; border: 1px solid {c["border"]}; padding: 6px; }}
    QMenu {{ background: {c["surface"]}; border: 1px solid {c["border"]}; padding: 6px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {c["surface_alt"]}; color: {c["text"]}; }}
    QFrame#banner {{ background: {c["primary_soft"]}; border: 0; border-radius: 10px; }}
    QFrame#banner[kind="success"] {{ background: {c["success_soft"]}; }}
    QFrame#banner[kind="warning"] {{ background: {c["warning_soft"]}; }}
    QTextEdit#logTerminal {{ font-family: "Cascadia Code", "Consolas", monospace; font-size: 9pt; border: 0; background: {c["surface"]}; }}
    QFrame#sourceCard {{ background: {c["surface"]}; border: 1px solid {c["border"]}; border-radius: 14px; }}
    QFrame#sourceCard:hover {{ border-color: {c["primary"]}; }}
    QFrame#sourceCard[selected="true"] {{ background: {c["primary_soft"]}; border: 2px solid {c["primary"]}; }}
    QLabel#sourceCardTitle {{ font-size: 12pt; font-weight: 600; }}
    QLabel#sourceCardDescription {{ color: {c["muted"]}; font-size: 9pt; }}
    QLabel#sourceCardSelectionBadge {{ background: {c["primary"]}; color: {c["on_primary"]}; border-radius: 9px;
        padding: 2px 10px; font-size: 8pt; font-weight: 700; }}
    QLabel#metric, QLabel#metricCardValue, QLabel#consolidationMetricValue {{ font-size: 18pt; font-weight: 600; }}
    QLabel#metricCardTitle {{ color: {c["muted"]}; font-size: 9pt; font-weight: 600; }}
    QLabel#consolidationStepNumber {{ background: {c["primary"]}; color: {c["on_primary"]}; border-radius: 13px; font-weight: 700; }}
    QLabel#consolidationPreviewStatus[stale="true"] {{ color: {c["warning"]}; }}
    QLabel#consolidationEmpty {{ color: {c["muted"]}; padding: 28px; }}
    QLabel#connectionState {{ color: {c["muted"]}; }}
    """


def apply_theme(app: QCoreApplication | None, mode: str) -> None:
    global _current
    if not isinstance(app, QApplication):
        return
    if mode == "system":
        dark = app.styleHints().colorScheme().name == "Dark"
    else:
        dark = mode == "dark"
    colors = DARK if dark else LIGHT
    _current = colors
    app.setStyle("Fusion")
    palette = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "window"), (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "surface_alt"), (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.WindowText, "text"), (QPalette.ColorRole.Button, "surface"),
        (QPalette.ColorRole.ButtonText, "text"), (QPalette.ColorRole.Highlight, "primary"),
        (QPalette.ColorRole.HighlightedText, "on_primary"), (QPalette.ColorRole.Mid, "border"),
        (QPalette.ColorRole.PlaceholderText, "muted"), (QPalette.ColorRole.ToolTipBase, "surface"),
        (QPalette.ColorRole.ToolTipText, "text"), (QPalette.ColorRole.Link, "primary"),
    ):
        palette.setColor(role, QColor(colors[key]))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(colors))
