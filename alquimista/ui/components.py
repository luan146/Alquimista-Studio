from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap, QPolygon
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import (
    ACCENT_COLOR,
    CARD_BACKGROUND,
    CARD_HOVER_BACKGROUND,
    SELECTED_BACKGROUND_GRADIENT_END,
    SELECTED_BACKGROUND_GRADIENT_START,
    SELECTED_HOVER_GRADIENT_END,
    SELECTED_HOVER_GRADIENT_START,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

APP_TITLE = "ALQuimista Studio — Extração e consolidação"


class VisibleArrowComboBox(QComboBox):
    """Combo box with a consistently visible dropdown indicator."""

    def paintEvent(self, event: object) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(QPalette.ColorRole.Highlight)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        center_x = self.width() - 18
        center_y = self.height() // 2
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(center_x - 6, center_y - 3),
                    QPoint(center_x, center_y + 4),
                    QPoint(center_x + 6, center_y - 3),
                ]
            )
        )
        painter.end()


class FlowLayout(QLayout):
    """Wrap child widgets into rows when horizontal space runs out."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: list[Any] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: Any) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Any:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Any:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: Any) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size + QSize(2 * self._spacing, 2 * self._spacing)

    def _do_layout(self, rect: Any, test_only: bool) -> int:

        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self._spacing
        for item in self._items:
            wid = item.widget()
            if wid is not None:
                wid.setVisible(True)
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y()

NAVIGATION = [
    ("dashboard", "Dashboard"),
    ("sources", "Fontes"),
    ("connection", "Conexão"),
    ("selection", "Espaços e seleção"),
    ("markdown", "Markdown"),
    ("consolidation", "Consolidação"),
    ("extraction", "Extração e revisão"),
    ("results", "Resultados"),
]

NAV_ICON_INDEX = {
    "dashboard": 0,
    "sources": 1,
    "connection": 2,
    "pages": 3,
    "selection": 3,
    "markdown": 5,
    "consolidation": 6,
    "extraction": 7,
    "review": 7,
    "output": 7,
    "results": 8,
    "settings": 9,
}

BUTTON_ICON_INDEX = {
    "🔎": 0,
    "←": 0,
    "🔐": 2,
    "🌐": 3,
    "🗑": 9,
    "🗑️": 9,
    "🔌": 2,
    "🌳": 3,
    "👁": 7,
    "✅": 7,
    "⬜": 4,
    "❓": 8,
    "📦": 6,
    "🚀": 6,
    "▶": 7,
    "🔄": 7,
    "⏹": 2,
    "🔁": 7,
    "📋": 12,
    "📁": 13,
    "🧾": 12,
    "🛠": 9,
    "💾": 15,
    "➕": 15,
    "＋": 15,
    "📂": 13,
    "↺": 9,
    "🔑": 2,
}


def repair_mojibake(text: str) -> str:
    """Repair UTF-8 text decoded once through a legacy code page.

    A few older page builders still pass values such as ``Conexão`` or
    ``🔐``.  Repairing them at this shared widget boundary keeps the visual
    components compatible while the page builders are migrated separately.
    """
    repaired = str(text)
    for _ in range(2):
        if not any(marker in repaired for marker in ("Ã", "Â", "â", "ðŸ", "�", "�")):
            break
        try:
            # CP1252 is the usual source of the visible ``ðŸ...`` form.  A
            # handful of CP1252 punctuation characters are outside Latin-1,
            # so translate those code points back to their original bytes.
            cp1252_symbols = "€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ"
            cp1252_codes = (
                0x80, 0x82, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88,
                0x89, 0x8A, 0x8B, 0x8C, 0x8E, 0x91, 0x92, 0x93,
                0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0x9B,
                0x9C, 0x9E, 0x9F,
            )
            cp1252_reverse = dict(zip(cp1252_symbols, cp1252_codes, strict=True))
            cp1252_bytes = bytes(
                ord(char)
                if ord(char) < 256
                else cp1252_reverse[char]
                for char in repaired
            )
            candidate = cp1252_bytes.decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError):
            break
        if candidate == repaired:
            break
        repaired = candidate
    return repaired


def repair_mojibake_text(func: Any) -> Any:
    """Repair mojibake in string arguments at a UI boundary."""
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        repaired_args = tuple(
            repair_mojibake(value) if isinstance(value, str) else value
            for value in args
        )
        repaired_kwargs = {
            key: repair_mojibake(value) if isinstance(value, str) else value
            for key, value in kwargs.items()
        }
        return func(*repaired_args, **repaired_kwargs)

    return wrapper


def _button_presentation(text: str) -> tuple[str, int | None]:
    text = repair_mojibake(text)
    for prefix, index in sorted(BUTTON_ICON_INDEX.items(), key=lambda item: len(item[0]), reverse=True):
        if text.startswith(prefix):
            return text[len(prefix) :].lstrip(), index
    return text, None


class AlchemistIconAtlas:
    """Loads the generated RPG/alchemy icon atlas and exposes individual cells."""

    _pixmap: QPixmap | None = None
    _path = Path(__file__).resolve().parents[2] / "assets" / "icons" / "alchemist_icon_atlas.png"

    @classmethod
    def _load(cls) -> QPixmap:
        if cls._pixmap is None:
            cls._pixmap = QPixmap(str(cls._path))
        return cls._pixmap

    @classmethod
    def pixmap(cls, index: int, size: int = 64) -> QPixmap:
        atlas = cls._load()
        if atlas.isNull():
            return QPixmap()
        safe_index = index % 16 if index >= 0 else 0
        cell_width = atlas.width() // 4
        cell_height = atlas.height() // 4
        cell = atlas.copy(
            (safe_index % 4) * cell_width,
            (safe_index // 4) * cell_height,
            cell_width,
            cell_height,
        )
        return cell.scaled(
            QSize(size, size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    @classmethod
    def icon(cls, index: int, size: int = 24) -> QIcon:
        pixmap = cls.pixmap(index, size)
        return QIcon(pixmap) if not pixmap.isNull() else QIcon()

    @classmethod
    def page_index(cls, fallback: str) -> int | None:
        fallback = repair_mojibake(fallback)
        return {
            "📚": 1,
            "🌳": 3,
            "☑": 4,
            "✍": 5,
            "⚙": 9,
            "📦": 6,
            "📊": 8,
            "🔧": 9,
            "🚀": 7,
            "🔒": 2,
        }.get(fallback)


def metric_card(
    title: str, value: str = "0", subtext: str = ""
) -> tuple[QFrame, QLabel, QLabel]:
    """Create a modern 2026 metric card with value, title and subtext."""
    frame = QFrame()
    frame.setObjectName("metricCard")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(4)

    title_label = QLabel(title)
    title_label.setObjectName("metricCardTitle")
    layout.addWidget(title_label)

    val_label = QLabel(value)
    val_label.setObjectName("metricCardValue")
    layout.addWidget(val_label)

    sub_label = QLabel(subtext)
    sub_label.setObjectName("metricCardSub")
    sub_label.setVisible(bool(subtext))
    layout.addWidget(sub_label)

    return frame, val_label, sub_label


def status_badge(text: str, level: str = "info") -> QLabel:
    """Create a colored status pill."""
    label = QLabel(text)
    obj_names = {
        "success": "statusBadgeSuccess",
        "warning": "statusBadgeWarning",
        "danger": "statusBadgeDanger",
        "info": "statusBadgeInfo",
    }
    label.setObjectName(obj_names.get(level, "statusBadge"))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def button(
    text: str, slot: Any, *, primary: bool = False, danger: bool = False
) -> QPushButton:
    clean_text, icon_index = _button_presentation(text)
    result = QPushButton(clean_text)
    result.setMinimumHeight(40)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if icon_index is not None:
        result.setIcon(AlchemistIconAtlas.icon(icon_index, 20))
        result.setIconSize(QSize(20, 20))
    result.setProperty("primary", primary)
    result.setProperty("danger", danger)
    result.clicked.connect(slot)
    return result


class GlowButton(QPushButton):
    """Push button with a subtle animated glow for important actions."""

    def __init__(self, text: str, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 5)
        self._shadow.setColor(QColor(accent))
        self._shadow.setBlurRadius(10)
        self.setGraphicsEffect(self._shadow)

        self._hover_animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_animation.setDuration(900)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._hover_animation.setStartValue(10)
        self._hover_animation.setKeyValueAt(0.5, 22)
        self._hover_animation.setEndValue(10)
        self._hover_animation.setLoopCount(-1)

        self._click_animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._click_animation.setDuration(280)
        self._click_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._click_animation.finished.connect(self._resume_hover_animation)
        self.pressed.connect(self._pulse_on_click)

    def enterEvent(self, event: object) -> None:
        if self._hover_animation.state() != QAbstractAnimation.State.Running:
            self._hover_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:
        self._hover_animation.stop()
        self._click_animation.stop()
        self._click_animation.setStartValue(self._shadow.blurRadius())
        self._click_animation.setEndValue(8)
        self._click_animation.start()
        super().leaveEvent(event)

    def _pulse_on_click(self) -> None:
        self._hover_animation.stop()
        self._click_animation.stop()
        self._click_animation.setStartValue(self._shadow.blurRadius())
        self._click_animation.setKeyValueAt(0.35, 30)
        self._click_animation.setEndValue(18)
        self._click_animation.start()

    def _resume_hover_animation(self) -> None:
        if self.underMouse():
            self._hover_animation.start()


def animated_button(
    text: str,
    slot: Any,
    *,
    primary: bool = False,
    danger: bool = False,
    accent: str = "#42B8BE",
) -> QPushButton:
    clean_text, icon_index = _button_presentation(text)
    result = GlowButton(clean_text, accent)
    result.setMinimumHeight(46)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if icon_index is not None:
        result.setIcon(AlchemistIconAtlas.icon(icon_index, 22))
        result.setIconSize(QSize(22, 22))
    result.setObjectName("connectionAction")
    result.setProperty("primary", primary)
    result.setProperty("danger", danger)
    result.clicked.connect(slot)
    return result


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)
    return frame, layout


def page_header(title: str, subtitle: str, emoji: str) -> tuple[QWidget, QVBoxLayout]:
    title = repair_mojibake(title)
    subtitle = repair_mojibake(subtitle)
    emoji = repair_mojibake(emoji)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(26, 22, 26, 22)
    layout.setSpacing(14)
    row = QHBoxLayout()
    icon = QLabel()
    icon.setObjectName("heroIcon")
    icon_index = AlchemistIconAtlas.page_index(emoji)
    icon_pixmap = (
        AlchemistIconAtlas.pixmap(icon_index, 62)
        if icon_index is not None
        else QPixmap()
    )
    if icon_pixmap.isNull():
        icon.setText(emoji)
    else:
        icon.setPixmap(icon_pixmap)
    row.addWidget(icon)
    text = QVBoxLayout()
    heading = QLabel(title)
    heading.setObjectName("pageTitle")
    detail = QLabel(subtitle)
    detail.setObjectName("subtitle")
    detail.setWordWrap(True)
    text.addWidget(heading)
    text.addWidget(detail)
    row.addLayout(text, 1)
    layout.addLayout(row)
    return page, layout


class HorizontalScrollArea(QScrollArea):
    """Horizontal card scroller that treats the normal wheel as sideways input."""

    def scroll_by_wheel(self, delta: int) -> None:
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)


    def viewportEvent(self, event: object) -> bool:
        event_type = getattr(event, "type", lambda: None)()
        if event_type == QEvent.Type.Wheel:
            delta = getattr(event, "angleDelta", lambda: None)()
            amount = delta.y() if delta is not None else 0
            modifiers = getattr(
                event,
                "modifiers",
                lambda: Qt.KeyboardModifier.NoModifier,
            )()
            horizontal_requested = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            if amount and horizontal_requested and self.horizontalScrollBar().maximum() > 0:
                self.scroll_by_wheel(amount)
                getattr(event, "accept", lambda: None)()
                return True
        return super().viewportEvent(event)


class SourceCard(QFrame):
    """Clickable knowledge-source tile used on the welcome page."""

    clicked = Signal(str)
    double_clicked = Signal(str)
    right_clicked = Signal(str)
    selection_toggled = Signal(bool)

    def __init__(
        self,
        source_type: str,
        title: str,
        subtitle: str = "",
        icon: int | str = "✦",
        accent: str = "#7FE4B5",
        description: str = "",
        visibility: str | None = None,
        visibility_kind: str = "public",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        source_type = repair_mojibake(source_type)
        title = repair_mojibake(title)
        subtitle = repair_mojibake(subtitle)
        icon = repair_mojibake(icon) if isinstance(icon, str) else icon
        description = repair_mojibake(description)
        visibility = repair_mojibake(visibility) if visibility else visibility
        self.source_type = source_type
        self._accent = accent
        self._selected = False
        self.setObjectName("sourceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMinimumHeight(218)
        self.setMaximumHeight(280)
        self.setStyleSheet(
            "QFrame#sourceCard {"
            f" background-color: {CARD_BACKGROUND};"
            f" border: 1px solid {accent};"
            " border-radius: 18px;"
            "}"
            "QFrame#sourceCard:hover {"
            f" background-color: {CARD_HOVER_BACKGROUND};"
            f" border: 2px solid {accent};"
            "}"
        )

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 8)
        self._shadow.setColor(QColor(accent))
        self._shadow.setBlurRadius(14)
        self.setGraphicsEffect(self._shadow)

        self._hover_animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._hover_animation.setDuration(900)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._hover_animation.setStartValue(16)
        self._hover_animation.setKeyValueAt(0.5, 30)
        self._hover_animation.setEndValue(16)
        self._hover_animation.setLoopCount(-1)

        self._click_animation = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._click_animation.setDuration(280)
        self._click_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(8)

        self.selection_badge = QLabel("✓ SELECIONADO")
        self.selection_badge.setObjectName("sourceCardSelectionBadge")
        self.selection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selection_badge.setStyleSheet(
            f"color: #0C1D2A; background: {ACCENT_COLOR}; border-radius: 10px; "
            "padding: 3px 12px; font-size: 8pt; font-weight: 800;"
        )
        self.selection_badge.setFixedHeight(22)
        self.selection_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.selection_badge.setVisible(False)
        layout.addWidget(self.selection_badge, 0, Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon_label.setObjectName("sourceCardIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if isinstance(icon, int):
            icon_pixmap = AlchemistIconAtlas.pixmap(icon, 76)
            if icon_pixmap.isNull():
                icon_label.setText("✦")
            else:
                icon_label.setPixmap(icon_pixmap)
        else:
            icon_label.setText(icon)
            icon_label.setStyleSheet(f"font-size: 27pt; color: {accent};")
        icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("sourceCardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setFixedHeight(48)
        title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        title_label.setStyleSheet(f"font-size: 15pt; font-weight: 700; color: {TEXT_PRIMARY};")
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)

        if visibility:
            visibility_label = QLabel(visibility)
            visibility_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if visibility_kind == "private":
                color, background = "#C5A5FF", "#302744"
            else:
                color, background = "#19C98A", "#103B38"
            visibility_label.setStyleSheet(
                f"color: {color}; background: {background}; border-radius: 9px; "
                "padding: 3px 10px; font-size: 8pt; font-weight: 700;"
            )
            visibility_label.setFixedHeight(22)
            visibility_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(visibility_label, 0, Qt.AlignmentFlag.AlignCenter)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedWidth(136)
        line.setStyleSheet(f"color: {accent}; background: {accent}; max-height: 1px;")
        layout.addWidget(line, 0, Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description or subtitle)
        description_label.setObjectName("sourceCardDescription")
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(f"font-size: 10pt; color: {TEXT_SECONDARY};")
        description_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(description_label, 1)

        arrow = QLabel("›")
        arrow.setObjectName("sourceCardArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        arrow.setStyleSheet(f"font-size: 18pt; color: {accent}; font-weight: 600;")
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(arrow)

    @property
    def selected(self) -> bool:
        return getattr(self, "_selected", False)

    def set_selected(self, selected: bool, animate: bool = True) -> None:
        self._selected = selected
        if hasattr(self, "selection_badge"):
            self.selection_badge.setVisible(selected)
        if selected:
            self.setStyleSheet(
                "QFrame#sourceCard {"
                f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SELECTED_BACKGROUND_GRADIENT_START}, stop:1 {SELECTED_BACKGROUND_GRADIENT_END});"
                f" border: 2px solid {ACCENT_COLOR};"
                " border-radius: 18px;"
                "}"
                "QFrame#sourceCard:hover {"
                f" background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {SELECTED_HOVER_GRADIENT_START}, stop:1 {SELECTED_HOVER_GRADIENT_END});"
                f" border: 3px solid {ACCENT_COLOR};"
                "}"
            )
            self._shadow.setColor(QColor(ACCENT_COLOR))
            if animate:
                self._click_animation.stop()
                self._click_animation.setStartValue(14)
                self._click_animation.setKeyValueAt(0.4, 34)
                self._click_animation.setEndValue(24)
                self._click_animation.start()
            else:
                self._shadow.setBlurRadius(24)
        else:
            self.setStyleSheet(
                "QFrame#sourceCard {"
                f" background-color: {CARD_BACKGROUND};"
                f" border: 1px solid {self._accent};"
                " border-radius: 18px;"
                "}"
                "QFrame#sourceCard:hover {"
                f" background-color: {CARD_HOVER_BACKGROUND};"
                f" border: 2px solid {self._accent};"
                "}"
            )
            self._shadow.setColor(QColor(self._accent))
            self._shadow.setBlurRadius(14)
        self.selection_toggled.emit(selected)

    def toggle_selected(self) -> None:
        self.set_selected(not self.selected)

    def _set_glow_radius(self, value: float) -> None:
        self._shadow.setBlurRadius(value)

    def _get_glow_radius(self) -> float:
        return self._shadow.blurRadius()

    glow_radius = Property(float, _get_glow_radius, _set_glow_radius)

    def enterEvent(self, event: object) -> None:
        if self._hover_animation.state() != QAbstractAnimation.State.Running:
            self._hover_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:
        self._hover_animation.stop()
        self._click_animation.stop()
        self._click_animation.setStartValue(self._shadow.blurRadius())
        self._click_animation.setEndValue(24 if self.selected else 14)
        self._click_animation.start()
        super().leaveEvent(event)

    def wheelEvent(self, event: object) -> None:
        ancestor = self.parentWidget()
        while ancestor is not None:
            if isinstance(ancestor, HorizontalScrollArea):
                delta = getattr(event, "angleDelta", lambda: None)()
                amount = delta.y() if delta is not None else 0
                if amount:
                    ancestor.scroll_by_wheel(amount)
                    getattr(event, "accept", lambda: None)()
                    return
                break
            ancestor = ancestor.parentWidget()
        super().wheelEvent(event)

    def mousePressEvent(self, event: object) -> None:
        btn = getattr(event, "button", lambda: None)()
        if btn == Qt.MouseButton.LeftButton:
            self._click_animation.stop()
            self._click_animation.setStartValue(self._shadow.blurRadius())
            self._click_animation.setKeyValueAt(0.35, 38)
            self._click_animation.setEndValue(24 if self.selected else 14)
            self._click_animation.start()
            self.clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        elif btn == Qt.MouseButton.RightButton:
            self.toggle_selected()
            self.right_clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: object) -> None:
        getattr(event, "accept", lambda: None)()

    def mouseDoubleClickEvent(self, event: object) -> None:
        if getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: object) -> None:
        if getattr(event, "key", lambda: None)() in {
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        }:
            self.clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        super().keyPressEvent(event)


class CollapsibleSection(QFrame):
    """Animated, themed section used for grouped Markdown options."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        icon: str = "▣",
        *,
        expanded: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = repair_mojibake(title)
        self._icon = repair_mojibake(icon)
        self.setObjectName("markdownSection")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QPushButton()
        self.header.setObjectName("markdownSectionHeader")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setCheckable(True)
        self.header.clicked.connect(self.set_expanded)
        layout.addWidget(self.header)

        self.content = QWidget()
        self.content.setObjectName("markdownSectionContent")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(14, 8, 14, 12)
        self.content_layout.setSpacing(4)
        layout.addWidget(self.content)

        self._animation = QPropertyAnimation(self.content, b"maximumHeight", self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_expanded(expanded, animate=False)

    def addWidget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def addLayout(self, child_layout: Any) -> None:
        self.content_layout.addLayout(child_layout)

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        self.header.setChecked(expanded)
        self.header.setText(
            f"{self._icon}  {self._title}                                  "
            f"{'⌃' if expanded else '⌄'}"
        )
        target = self.content_layout.sizeHint().height() if expanded else 0
        if animate:
            current = self.content.maximumHeight()
            if current >= 16_000_000:
                current = self.content_layout.sizeHint().height()
            self._animation.stop()
            self._animation.setStartValue(current)
            self._animation.setEndValue(target)
            self._animation.start()
        else:
            self.content.setMaximumHeight(target if not expanded else 16_777_215)
        self.toggled.emit(expanded)


class SortableTreeItem(QTreeWidgetItem):
    SORT_ROLE = int(Qt.ItemDataRole.UserRole) + 20

    def __lt__(self, other: QTreeWidgetItem) -> bool:
        column = self.treeWidget().sortColumn() if self.treeWidget() else 0
        left = self.data(column, self.SORT_ROLE)
        right = other.data(column, self.SORT_ROLE)
        if left is not None and right is not None:
            return left < right
        return self.text(column).casefold() < other.text(column).casefold()


class VisibilityBadgeDelegate(QStyledItemDelegate):
    """Paint the complete title cell without creating a widget per row."""

    VISIBILITY_ROLE = int(Qt.ItemDataRole.UserRole) + 30
    VISIBILITY_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 31
    RICH_ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 32
    TITLE_ROLE = int(Qt.ItemDataRole.UserRole) + 33
    ICON_ROLE = int(Qt.ItemDataRole.UserRole) + 34
    SOURCE_ROLE = int(Qt.ItemDataRole.UserRole) + 35
    CONTAINER_ROLE = int(Qt.ItemDataRole.UserRole) + 36
    DOCUMENT_ROLE = int(Qt.ItemDataRole.UserRole) + 37

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        badge = repair_mojibake(str(index.data(self.VISIBILITY_ROLE) or ""))
        title = repair_mojibake(str(index.data(self.TITLE_ROLE) or ""))
        icon = repair_mojibake(str(index.data(self.ICON_ROLE) or ""))
        if not title:
            painter.save()
            try:
                painter.setClipRect(option.rect, Qt.ClipOperation.IntersectClip)
                super().paint(painter, option, index)
            finally:
                painter.restore()
            return

        view_option = QStyleOptionViewItem(option)
        self.initStyleOption(view_option, index)
        view_option.text = ""
        view_option.icon = QIcon()

        widget = view_option.widget
        style = widget.style() if widget is not None else None
        if style is None:
            painter.save()
            try:
                painter.setClipRect(option.rect, Qt.ClipOperation.IntersectClip)
                super().paint(painter, option, index)
            finally:
                painter.restore()
            return

        cell_rect = QRectF(option.rect).normalized()
        text_rect = QRectF(
            style.subElementRect(
                QStyle.SubElement.SE_ItemViewItemText, view_option, widget
            )
        ).intersected(cell_rect)
        icon_width = view_option.fontMetrics.horizontalAdvance(icon) if icon else 0
        icon_gap = 8 if icon else 0
        badge_width = view_option.fontMetrics.horizontalAdvance(badge) + 16 if badge else 0
        badge_height = min(18.0, max(16.0, float(text_rect.height() - 4)))
        available_width = max(0.0, text_rect.width())

        painter.save()
        try:
            painter.setClipRect(option.rect, Qt.ClipOperation.IntersectClip)
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem,
                view_option,
                painter,
                widget,
            )
            if text_rect.isEmpty():
                return

            painter.setFont(view_option.font)
            text_color = (
                QPalette.ColorRole.HighlightedText
                if view_option.state & QStyle.StateFlag.State_Selected
                else QPalette.ColorRole.Text
            )
            painter.setPen(view_option.palette.color(text_color))
            if icon:
                icon_rect = QRectF(
                    text_rect.left(), text_rect.top(), icon_width, text_rect.height()
                )
                painter.drawText(icon_rect, Qt.AlignmentFlag.AlignVCenter, icon)

            title_rect = QRectF(
                text_rect.left() + icon_width + icon_gap,
                text_rect.top(),
                max(
                    0.0,
                    available_width
                    - icon_width
                    - icon_gap
                    - (badge_width + 8 if badge else 0),
                ),
                text_rect.height(),
            )
            elided_title = view_option.fontMetrics.elidedText(
                title, Qt.TextElideMode.ElideRight, int(title_rect.width())
            )
            title_width = min(
                title_rect.width(),
                view_option.fontMetrics.horizontalAdvance(elided_title),
            )
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided_title,
            )
            if not badge:
                return

            badge_rect = QRectF(
                min(
                    title_rect.left() + title_width + 8,
                    text_rect.right() - badge_width,
                ),
                text_rect.center().y() - badge_height / 2,
                min(badge_width, text_rect.width()),
                badge_height,
            ).intersected(cell_rect)
            if badge_rect.isEmpty():
                return

            kind = str(index.data(self.VISIBILITY_KIND_ROLE) or "unknown")
            if kind == "public":
                foreground, background = QColor("#19C98A"), QColor("#103B38")
            elif kind == "private":
                foreground, background = QColor("#C5A5FF"), QColor("#302744")
            elif kind == "root":
                foreground, background = QColor("#D6B9FF"), QColor("#33294B")
            else:
                foreground, background = QColor("#A7B5C4"), QColor("#273645")
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(badge_rect, 9, 9)
            painter.setPen(foreground)
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge)
        finally:
            painter.restore()


class ResponsiveOutputControls(QWidget):
    """Keep the output path usable when the review card becomes narrow."""

    def __init__(self, path_edit: QWidget, action_buttons: list[QWidget]) -> None:
        super().__init__()
        self.path_edit = path_edit
        self.action_buttons = action_buttons
        self._compact: bool | None = None
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(8)
        self._layout.setVerticalSpacing(8)
        self._apply_layout(True)

    def resizeEvent(self, event: object) -> None:
        compact = self.width() < 560
        if compact != self._compact:
            self._apply_layout(compact)
        super().resizeEvent(event)

    def _apply_layout(self, compact: bool) -> None:
        self._compact = compact
        while self._layout.count():
            self._layout.takeAt(0)

        if compact:
            self._layout.addWidget(self.path_edit, 0, 0, 1, len(self.action_buttons))
            for column, widget in enumerate(self.action_buttons):
                self._layout.addWidget(widget, 1, column)
                self._layout.setColumnStretch(column, 1)
        else:
            self._layout.addWidget(self.path_edit, 0, 0)
            self._layout.setColumnStretch(0, 1)
            for column, widget in enumerate(self.action_buttons, start=1):
                self._layout.addWidget(widget, 0, column)


def timestamp_sort_value(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0
