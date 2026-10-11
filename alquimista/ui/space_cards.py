"""Space cards on the Seleção page, painted by a delegate (no widget per card, so 300+ spaces stay fast)."""
from __future__ import annotations

import zlib
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

from .i18n import translate_text
from .theme import current_colors, is_dark

# (fundo, letra) claros e escuros, escolhidos pelo nome do espaço.
_TILES_LIGHT = [("#DCFCE7", "#15803D"), ("#FEF3C7", "#B45309"), ("#EDE9FE", "#6D28D9"),
                ("#DBEAFE", "#1D4ED8"), ("#FFE4E6", "#BE123C"), ("#E0F2FE", "#0369A1")]
_TILES_DARK = [("#14532D", "#86EFAC"), ("#713F12", "#FDE68A"), ("#3B0764", "#DDD6FE"),
               ("#1E3A8A", "#BFDBFE"), ("#881337", "#FECDD3"), ("#0C4A6E", "#BAE6FD")]


def tile_colors(name: str) -> tuple[str, str]:
    palette = _TILES_DARK if is_dark() else _TILES_LIGHT
    return palette[zlib.crc32(name.encode("utf-8")) % len(palette)]


class SpaceCardDelegate(QStyledItemDelegate):
    NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 40
    PAGES_ROLE = int(Qt.ItemDataRole.UserRole) + 41
    SELECTED_ROLE = int(Qt.ItemDataRole.UserRole) + 42
    LOADED_ROLE = int(Qt.ItemDataRole.UserRole) + 43
    SIZE = QSize(224, 112)

    whole_toggled = Signal(str, bool)
    open_requested = Signal(str)

    @staticmethod
    def pill_rect(rect: QRect) -> QRect:
        return QRect(rect.right() - 76, rect.top() + 12, 64, 22)

    def sizeHint(self, _option: QStyleOptionViewItem, _index: Any) -> QSize:
        return self.SIZE

    @staticmethod
    def _counts(index: Any) -> tuple[int, int, bool]:
        pages = int(index.data(SpaceCardDelegate.PAGES_ROLE) or 0)
        selected = int(index.data(SpaceCardDelegate.SELECTED_ROLE) or 0)
        return pages, selected, bool(pages) and selected >= pages

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
        c = current_colors()
        name = str(index.data(self.NAME_ROLE) or "")
        pages, selected, whole = self._counts(index)
        loaded = bool(index.data(self.LOADED_ROLE))
        rect = QRectF(option.rect).adjusted(4, 4, -4, -4)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        border = QColor(c["primary"] if whole or hover else c["border"])
        painter.setPen(QPen(border, 2 if whole else 1))
        painter.setBrush(QColor(c["surface"]))
        painter.drawRoundedRect(rect, 12, 12)

        tile_bg, tile_fg = tile_colors(name)
        tile = QRectF(rect.left() + 12, rect.top() + 12, 30, 30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tile_bg))
        painter.drawRoundedRect(tile, 9, 9)
        font = QFont(option.font)
        bold = QFont(font)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(tile_fg))
        painter.drawText(tile, Qt.AlignmentFlag.AlignCenter, (name[:1] or "?").upper())

        pill = QRectF(self.pill_rect(option.rect))
        painter.setPen(Qt.PenStyle.NoPen if whole else QPen(QColor(c["border"]), 1))
        painter.setBrush(QColor(c["primary"]) if whole else Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(pill, 11, 11)
        painter.setPen(QColor(c["on_primary"] if whole else c["muted"]))
        small = QFont(font)
        small.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
        small.setBold(True)
        painter.setFont(small)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, translate_text("Inteiro"))

        painter.setFont(bold)
        painter.setPen(QColor(c["text"]))
        title = QRectF(rect.left() + 12, rect.top() + 50, rect.width() - 24, 20)
        painter.drawText(title, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         painter.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(title.width())))
        small.setBold(False)
        painter.setFont(small)
        painter.setPen(QColor(c["muted"]))
        if selected:
            detail = translate_text("{selected} de {pages} páginas").format(selected=selected, pages=pages or "?")
        elif loaded:
            detail = translate_text("Nada marcado · {pages} páginas").format(pages=pages)
        else:
            detail = translate_text("Ainda não aberto")
        painter.drawText(QRectF(rect.left() + 12, rect.top() + 70, rect.width() - 24, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)

        bar = QRectF(rect.left() + 12, rect.bottom() - 14, rect.width() - 24, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(c["surface_alt"]))
        painter.drawRoundedRect(bar, 2, 2)
        if pages and selected:
            painter.setBrush(QColor(c["primary"]))
            painter.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * min(1.0, selected / pages), 4), 2, 2)
        painter.restore()

    def editorEvent(self, event: QEvent, _model: Any, option: QStyleOptionViewItem, index: Any) -> bool:
        if event.type() != QEvent.Type.MouseButtonRelease or not isinstance(event, QMouseEvent):
            return False
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        container_id = str(index.data(Qt.ItemDataRole.UserRole))
        if self.pill_rect(option.rect).contains(event.position().toPoint()):
            _pages, _selected, whole = self._counts(index)
            self.whole_toggled.emit(container_id, not whole)
        else:
            self.open_requested.emit(container_id)
        return True
