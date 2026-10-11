from __future__ import annotations

from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPixmap,
    QPolygon,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QBoxLayout,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTabWidget,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .icons import AUTH_ICONS, EMOJI_ICONS, SYSTEM_ICONS, svg_icon, svg_pixmap

APP_TITLE = "ALQuimista Studio — Extração e consolidação"


class VisibleArrowComboBox(QComboBox):
    """Combo box with a consistently visible dropdown indicator."""

    def paintEvent(self, event: QPaintEvent) -> None:
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

# Home plus the five workflow steps shown in the sidebar.
NAVIGATION = [
    ("dashboard", "Início"),
    ("sources", "Fontes"),
    ("selection", "Seleção"),
    ("format", "Saída"),
    ("extraction", "Executar"),
    ("results", "Resultados"),
]
WORKFLOW_STEPS = [key for key, _label in NAVIGATION if key != "dashboard"]

# Older page keys (8-step layout) still route somewhere sensible; the tab index
# selects Markdown (0) or Pacotes (1) inside the "Saída" page.
PAGE_ALIASES: dict[str, tuple[str, int | None]] = {
    "connection": ("sources", None),
    "markdown": ("format", 0),
    "consolidation": ("format", 1),
    "review": ("extraction", None),
    "output": ("extraction", None),
}

NAV_ICON_INDEX = {
    "dashboard": 0,
    "sources": 1,
    "connection": 2,
    "pages": 3,
    "selection": 3,
    "markdown": 5,
    "consolidation": 6,
    "format": 5,
    "extraction": 7,
    "review": 7,
    "output": 7,
    "results": 8,
    "settings": 9,
}

BUTTON_ICON_INDEX = {
    "🔎": 14,
    "←": 13,
    "🔐": 2,
    "🌐": 3,
    "🗑": 12,
    "🗑️": 12,
    "🔌": 14,
    "🌳": 3,
    "👁": 3,
    "✅": 7,
    "⬜": 15,
    "❓": 8,
    "📦": 5,
    "🚀": 6,
    "▶": 6,
    "🔄": 5,
    "⏹": 15,
    "🔁": 6,
    "📋": 1,
    "📁": 11,
    "🧾": 1,
    "🛠": 8,
    "💾": 9,
    "➕": 10,
    "＋": 10,
    "📂": 11,
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
    """Interface icons come from assets/icons/ui (SVG); connector icons still come from the generated atlas."""

    _connector_pixmap_cache: QPixmap | None = None
    _connector_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "icons"
        / "alchemist_connector_atlas.png"
    )
    _fallback_path = (
        Path(__file__).resolve().parents[2]
        / "assets"
        / "icons"
        / "alchemist_icon_atlas.png"
    )

    @classmethod
    def _load_connectors(cls) -> QPixmap:
        if cls._connector_pixmap_cache is None:
            cls._connector_pixmap_cache = QPixmap(str(cls._connector_path))
            if cls._connector_pixmap_cache.isNull():
                cls._connector_pixmap_cache = QPixmap(str(cls._fallback_path))
        return cls._connector_pixmap_cache

    @classmethod
    def _cell(
        cls, atlas: QPixmap, index: int, columns: int, rows: int, size: int
    ) -> QPixmap:
        if atlas.isNull():
            return QPixmap()
        safe_index = index % (columns * rows) if index >= 0 else 0
        cell_width = atlas.width() // columns
        cell_height = atlas.height() // rows
        cell = atlas.copy(
            (safe_index % columns) * cell_width,
            (safe_index // columns) * cell_height,
            cell_width,
            cell_height,
        )
        return cell.scaled(
            QSize(size, size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    @classmethod
    def pixmap(cls, index: int, size: int = 64) -> QPixmap:
        return svg_pixmap(SYSTEM_ICONS[index % len(SYSTEM_ICONS)], size)

    @classmethod
    def connector_pixmap(cls, index: int, size: int = 64) -> QPixmap:
        return cls._cell(cls._load_connectors(), index, 8, 4, size)

    @classmethod
    def connector_icon(cls, index: int, size: int = 24) -> QIcon:
        pixmap = cls.connector_pixmap(index, size)
        return QIcon(pixmap) if not pixmap.isNull() else QIcon()

    @classmethod
    def auth_pixmap(cls, index: int, size: int = 24) -> QPixmap:
        return svg_pixmap(AUTH_ICONS[index % len(AUTH_ICONS)], size)

    @classmethod
    def auth_icon(cls, index: int, size: int = 24) -> QIcon:
        return svg_icon(AUTH_ICONS[index % len(AUTH_ICONS)], size)

    @classmethod
    def icon(cls, index: int, size: int = 24) -> QIcon:
        return svg_icon(SYSTEM_ICONS[index % len(SYSTEM_ICONS)], size)

    @classmethod
    def page_index(cls, fallback: str) -> int | None:
        fallback = repair_mojibake(fallback)
        return {
            "📚": 1,
            "🌳": 3,
            "☑": 3,
            "✍": 4,
            "⚙": 8,
            "📦": 5,
            "📊": 7,
            "🔧": 8,
            "🚀": 6,
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


def animated_button(
    text: str,
    slot: Any,
    *,
    primary: bool = False,
    danger: bool = False,
    accent: str = "",
) -> QPushButton:
    """Kept for old callers; the glow animation was dropped in the new look (accent is ignored)."""
    result = button(text, slot, primary=primary, danger=danger)
    result.setObjectName("connectionAction")
    result.setMinimumHeight(44)
    return result


def card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)
    return frame, layout


def chip(text: str, kind: str = "neutral") -> QLabel:
    """Pill label; kind is neutral, accent, success, warning or danger (styled by theme.py)."""
    label = QLabel(text)
    label.setObjectName("chip")
    label.setProperty("kind", kind)
    return label


def set_chip_kind(label: QLabel, kind: str) -> None:
    label.setProperty("kind", kind)
    label.style().unpolish(label)
    label.style().polish(label)


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


class SegmentedControl(QFrame):
    """Pill buttons side by side that drive an existing combo, tab widget or stack (the source of truth)."""

    changed = Signal(object)

    def __init__(
        self,
        options: list[tuple[Any, ...]],
        *,
        vertical: bool = False,
        tiles: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        self.setProperty("vertical", vertical)
        self.setProperty("tiles", tiles)
        layout: QBoxLayout = QVBoxLayout(self) if vertical else QHBoxLayout(self)
        if vertical or tiles:
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(8 if tiles else 2)
        self._group = QButtonGroup(self)
        self._values: list[Any] = []
        for index, option in enumerate(options):
            label, value = option[0], option[1]
            icon = option[2] if len(option) > 2 else None
            segment: QAbstractButton
            if tiles:
                segment = QToolButton()
                segment.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                segment.setIconSize(QSize(88, 52))
            else:
                segment = QPushButton()
            segment.setText(label)
            if icon is not None:
                segment.setIcon(icon)
            segment.setCheckable(True)
            segment.setCursor(Qt.CursorShape.PointingHandCursor)
            self._group.addButton(segment, index)
            layout.addWidget(segment)
            self._values.append(value)
        if vertical:
            layout.addStretch()
        self._group.idClicked.connect(lambda index: self.changed.emit(self._values[index]))

    def buttons(self) -> list[QAbstractButton]:
        return [self._group.button(index) for index in range(len(self._values))]

    def value(self) -> Any:
        index = self._group.checkedId()
        return self._values[index] if index >= 0 else None

    def set_value(self, value: Any) -> None:
        if value in self._values:
            self._group.button(self._values.index(value)).setChecked(True)
            return
        # A value without a segment (e.g. a filter picked from a menu) leaves none checked.
        self._group.setExclusive(False)
        for segment in self._group.buttons():
            segment.setChecked(False)
        self._group.setExclusive(True)

    def bind_combo(self, combo: QComboBox) -> SegmentedControl:
        self.set_value(combo.currentData())
        self.changed.connect(lambda value: combo.setCurrentIndex(combo.findData(value)))
        combo.currentIndexChanged.connect(lambda _index: self.set_value(combo.currentData()))
        return self

    def bind_stack(self, widget: QStackedWidget | QTabWidget) -> SegmentedControl:
        self.set_value(widget.currentIndex())
        self.changed.connect(widget.setCurrentIndex)
        widget.currentChanged.connect(self.set_value)
        return self

    def sync_enabled_from(self, combo: QComboBox) -> None:
        """Hide segments whose combo item is disabled (e.g. auth modes a platform doesn't accept)."""
        model = combo.model()
        for segment, value in zip(self.buttons(), self._values, strict=True):
            row = combo.findData(value)
            item = model.item(row) if hasattr(model, "item") and row >= 0 else None
            segment.setHidden(item is not None and not item.isEnabled())


def page_header(title: str, subtitle: str, emoji: str) -> tuple[QWidget, QVBoxLayout]:
    title = repair_mojibake(title)
    subtitle = repair_mojibake(subtitle)
    emoji = repair_mojibake(emoji)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(28, 20, 28, 20)
    layout.setSpacing(14)
    row = QHBoxLayout()
    row.setSpacing(14)
    icon = QLabel()
    icon.setObjectName("heroIcon")
    icon_index = AlchemistIconAtlas.page_index(emoji)
    if icon_index is None:
        icon.setText(emoji)
    else:
        icon.setPixmap(AlchemistIconAtlas.pixmap(icon_index, 40))
    row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
    text = QVBoxLayout()
    text.setSpacing(2)
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


    def viewportEvent(self, event: QEvent) -> bool:
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
        self._accent = accent  # kept for callers; colors come from theme.py
        self._selected = False
        self.setObjectName("sourceCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMinimumHeight(180)
        self.setMaximumHeight(230)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(8)

        self.selection_badge = QLabel("✓ SELECIONADO")
        self.selection_badge.setObjectName("sourceCardSelectionBadge")
        self.selection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.selection_badge.setFixedHeight(22)
        self.selection_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.selection_badge.setVisible(False)
        layout.addWidget(self.selection_badge, 0, Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon_label.setObjectName("sourceCardIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if isinstance(icon, int):
            icon_pixmap = AlchemistIconAtlas.connector_pixmap(icon, 64)
            if icon_pixmap.isNull():
                icon_label.setText("✦")
            else:
                icon_label.setPixmap(icon_pixmap)
        else:
            icon_label.setText(icon)
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
        title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)

        if visibility:
            visibility_label = chip(visibility, "danger" if visibility_kind == "private" else "success")
            visibility_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            visibility_label.setFixedHeight(22)
            visibility_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(visibility_label, 0, Qt.AlignmentFlag.AlignCenter)

        description_label = QLabel(description or subtitle)
        description_label.setObjectName("sourceCardDescription")
        description_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description_label.setWordWrap(True)
        description_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(description_label, 1)

        arrow = QLabel("›")
        arrow.setObjectName("sourceCardArrow")
        arrow.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        arrow.setStyleSheet("font-size: 18pt; font-weight: 600;")
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(arrow)

    @property
    def selected(self) -> bool:
        return getattr(self, "_selected", False)

    def set_selected(self, selected: bool, animate: bool = True) -> None:
        self._selected = selected
        if hasattr(self, "selection_badge"):
            self.selection_badge.setVisible(selected)
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.selection_toggled.emit(selected)

    def toggle_selected(self) -> None:
        self.set_selected(not self.selected)

    def wheelEvent(self, event: QWheelEvent) -> None:
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

    def mousePressEvent(self, event: QMouseEvent) -> None:
        btn = getattr(event, "button", lambda: None)()
        if btn == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        elif btn == Qt.MouseButton.RightButton:
            self.toggle_selected()
            self.right_clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        getattr(event, "accept", lambda: None)()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.source_type)
            getattr(event, "accept", lambda: None)()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
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
        kind = str(index.data(self.VISIBILITY_KIND_ROLE) or "unknown")
        icon_name = EMOJI_ICONS.get(icon)
        if icon_name == "pagina" and kind == "private":
            icon_name = "pagina_restrita"
        icon_size = 18
        icon_width = icon_size if icon_name else (view_option.fontMetrics.horizontalAdvance(icon) if icon else 0)
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
            if icon_name:
                painter.drawPixmap(
                    QPointF(text_rect.left(), text_rect.center().y() - icon_size / 2),
                    svg_pixmap(icon_name, icon_size),
                )
            elif icon:
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

    def resizeEvent(self, event: QResizeEvent) -> None:
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


_LegacySourceCard = SourceCard


def inform(parent: Any, title: str, message: str) -> None:
    """Informational message: a banner when the window has one, a dialog otherwise.

    Errors and confirmations keep using QMessageBox; only "FYI" messages come here.
    """
    notify = getattr(parent, "notify", None)
    if callable(notify):
        notify(message)
        return
    QMessageBox.information(parent, title, message)
