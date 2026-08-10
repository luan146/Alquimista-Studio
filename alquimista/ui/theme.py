from __future__ import annotations

# Shared component dimensions, colors, and animation timings.
SOURCE_CARD_MIN_HEIGHT = 218
SOURCE_CARD_MAX_HEIGHT = 280
BLUR_RADIUS_NORMAL = 14
BLUR_RADIUS_HOVER = 16
BLUR_RADIUS_CLICK = 24
ANIMATION_DURATION_HOVER = 900
ANIMATION_DURATION_CLICK = 280
CARD_BACKGROUND = "#18283A"
CARD_HOVER_BACKGROUND = "#20364A"
SELECTED_BACKGROUND_GRADIENT_START = "#1B3F54"
SELECTED_BACKGROUND_GRADIENT_END = "#112838"
SELECTED_HOVER_GRADIENT_START = "#22516C"
SELECTED_HOVER_GRADIENT_END = "#163347"
ACCENT_COLOR = "#7FE4B5"
TEXT_PRIMARY = "#F2F6FA"
TEXT_SECONDARY = "#A7B5C4"
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

LIGHT = {
    "window": "#F4F7FB",
    "surface": "#FFFFFF",
    "surface_alt": "#EEF3F8",
    "text": "#17212B",
    "muted": "#64748B",
    "border": "#DCE5EE",
    "primary": "#126E75",
    "primary_hover": "#0F5D63",
    "accent": "#7057C7",
    "success": "#16845B",
    "warning": "#B7791F",
    "danger": "#C2414B",
}

DARK = {
    "window": "#111820",
    "surface": "#18222D",
    "surface_alt": "#202D3A",
    "text": "#EDF3F8",
    "muted": "#A7B5C4",
    "border": "#314252",
    "primary": "#42B8BE",
    "primary_hover": "#63CCD1",
    "accent": "#A995F4",
    "success": "#52C991",
    "warning": "#E7B35A",
    "danger": "#F17882",
}


def stylesheet(colors: dict[str, str]) -> str:
    return f"""
    * {{
        font-family: "Segoe UI", "Segoe UI Emoji";
        font-size: 10pt;
        color: {colors["text"]};
    }}
    QMainWindow, QWidget#root {{
        background: {colors["window"]};
    }}
    QFrame#sidebar {{
        background: {colors["surface"]};
        border-right: 1px solid {colors["border"]};
    }}
    QLabel#brand {{
        font-size: 18pt;
        font-weight: 700;
        color: {colors["primary"]};
    }}
    QLabel#pageTitle {{
        font-size: 20pt;
        font-weight: 700;
    }}
    QLabel#subtitle, QLabel[muted="true"] {{
        color: {colors["muted"]};
    }}
    QLabel#heroIcon {{
        font-size: 44pt;
        color: {colors["accent"]};
    }}
    QFrame#connectionPanel {{
        background: {colors["surface"]};
        border: 1px solid {colors["primary"]};
        border-radius: 20px;
    }}
    QLabel#connectionIcon {{
        color: {colors["primary"]};
    }}
    QLabel#connectionLabel {{
        color: {colors["primary"]};
        font-weight: 700;
        font-size: 11pt;
    }}
    QLabel#connectionState {{
        color: {colors["primary"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["primary"]};
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
    }}
    QFrame#connectionSeparator {{
        color: {colors["primary"]};
        background: {colors["primary"]};
        max-height: 1px;
    }}
    QFrame#pageSummaryCard {{
        background: transparent;
        border: 0;
    }}
    QFrame#pageStat {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 12px;
    }}
    QLabel#pageStatValue {{
        color: {colors["text"]};
    }}
    QFrame#pageTableCard {{
        border: 1px solid {colors["primary"]};
        border-radius: 18px;
    }}
    QFrame#selectionIntroCard {{
        background: {colors["surface"]};
        border: 1px solid {colors["primary"]};
        border-radius: 18px;
    }}
    QFrame#markdownPreviewCard {{
        border: 1px solid {colors["primary"]};
        border-radius: 16px;
    }}
    QFrame#markdownSection {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 12px;
    }}
    QPushButton#markdownSectionHeader {{
        text-align: left;
        border: 0;
        border-radius: 11px;
        padding: 10px 12px;
        background: transparent;
        font-weight: 700;
    }}
    QPushButton#markdownSectionHeader:hover {{
        background: {colors["surface"]};
        color: {colors["primary"]};
    }}
    QFrame#markdownOptionRow {{
        background: transparent;
        border: 0;
        border-bottom: 1px solid {colors["border"]};
    }}
    QPushButton#markdownTextButton {{
        border: 0;
        padding: 4px 6px;
        background: transparent;
        color: {colors["primary"]};
    }}
    QPushButton#markdownTextButton:hover {{
        background: {colors["surface_alt"]};
    }}
    QLabel#markdownPreviewStatus {{
        color: {colors["success"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
        padding: 6px 10px;
        font-weight: 600;
    }}
    QFrame#consolidationControlsCard, QFrame#consolidationPreviewCard {{
        border-radius: 16px;
    }}
    QFrame#consolidationStep {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 12px;
    }}
    QLabel#consolidationStepNumber {{
        background: {colors["primary"]};
        color: white;
        border-radius: 13px;
        font-weight: 700;
    }}
    QFrame#consolidationSummary {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["primary"]};
        border-radius: 10px;
    }}
    QFrame#consolidationMetric {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
    }}
    QLabel#consolidationMetricValue {{
        font-size: 16pt;
        font-weight: 700;
    }}
    QLabel#consolidationPreviewStatus {{
        color: {colors["primary"]};
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 10px;
        padding: 6px 10px;
        font-weight: 600;
    }}
    QLabel#consolidationPreviewStatus[stale="true"] {{
        color: {colors["warning"]};
    }}
    QLabel#consolidationEmpty {{
        color: {colors["muted"]};
        padding: 28px;
    }}
   QComboBox#connectionCombo {{
       border: 1px solid {colors["primary"]};
       border-radius: 14px;
       padding: 10px 42px 10px 14px;
       font-size: 11pt;
   }}
   QComboBox#connectionCombo::drop-down {{
       subcontrol-origin: padding;
       subcontrol-position: top right;
       width: 36px;
       border-left: 1px solid {colors["primary"]};
       border-top-right-radius: 14px;
       border-bottom-right-radius: 14px;
       background: transparent;
   }}
  QComboBox#connectionCombo::down-arrow {{
       image: none;
       width: 0;
       height: 0;
   }}
  QPushButton#connectionAction {{
       min-height: 56px;
       border-radius: 12px;
       padding: 10px 18px;
       font-size: 11pt;
       font-weight: 600;
   }}
   QPushButton#connectionAction:hover {{
       border-width: 2px;
   }}
   QPushButton#connectionAction[danger="true"] {{
       background: transparent;
       border: 2px solid {colors["danger"]};
       color: {colors["danger"]};
   }}
  QPushButton#connectionAction[danger="true"]:hover {{
      background: {colors["danger"]};
      color: white;
      border: 2px solid {colors["danger"]};
      border-radius: 12px;
  }}
   QLabel#metric {{
       font-size: 24pt;
       font-weight: 700;
       color: {colors["primary"]};
   }}
    QFrame#card, QGroupBox {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 12px;
    }}
    QGroupBox {{
        margin-top: 12px;
        padding: 18px 12px 12px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
    }}
    QPushButton {{
        background: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 8px;
        padding: 8px 13px;
    }}
    QPushButton:hover {{
        border-color: {colors["primary"]};
        background: {colors["surface"]};
    }}
    QPushButton[primary="true"] {{
        background: {colors["primary"]};
        color: white;
        border-color: {colors["primary"]};
        font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{
        background: {colors["primary_hover"]};
    }}
    QPushButton[danger="true"] {{
        color: {colors["danger"]};
    }}
    QPushButton:disabled {{
        color: {colors["muted"]};
        background: {colors["surface_alt"]};
    }}
    QPushButton#navButton {{
        text-align: left;
        border: 0;
        border-radius: 9px;
        padding: 10px 12px;
        background: transparent;
    }}
    QPushButton#navButton:hover {{
        background: {colors["surface_alt"]};
    }}
    QPushButton#navButton:checked {{
        background: {colors["primary"]};
        color: white;
        font-weight: 600;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
        background: {colors["surface"]};
        border: 1px solid {colors["border"]};
        border-radius: 7px;
        padding: 7px;
        selection-background-color: {colors["primary"]};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 2px solid {colors["primary"]};
    }}
    QTreeWidget, QTableWidget, QListWidget {{
        background: {colors["surface"]};
        alternate-background-color: {colors["surface_alt"]};
        border: 1px solid {colors["border"]};
        border-radius: 9px;
        outline: 0;
    }}
    QWidget#treeTitleCell {{
        background: {colors["surface"]};
    }}
    QHeaderView::section {{
        background: {colors["surface_alt"]};
        border: 0;
        border-bottom: 1px solid {colors["border"]};
        padding: 8px;
        font-weight: 600;
    }}
    QProgressBar {{
        border: 0;
        background: {colors["surface_alt"]};
        border-radius: 6px;
        height: 12px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {colors["primary"]};
        border-radius: 6px;
    }}
    QScrollArea {{
        border: 0;
        background: transparent;
    }}
    """


def apply_theme(app: QApplication, mode: str) -> None:
    if mode == "system":
        is_dark = app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        colors = DARK if is_dark else LIGHT
    else:
        colors = DARK if mode == "dark" else LIGHT
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["primary"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(colors))

