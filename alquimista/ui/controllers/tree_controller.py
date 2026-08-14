from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHeaderView,
    QScrollArea,
    QStatusBar,
    QTreeWidget,
)

from ..components import SourceCard
from ..i18n import translate_text


class TreeController:
    """Manages tree presentation, column geometry and ordering, card reflow, and display pagination."""

    def __init__(
        self,
        settings: Any | None = None,
        status_bar: QStatusBar | None = None,
    ) -> None:
        self.settings = settings
        self.status_bar = status_bar
        self._space_card_animations: list[QPropertyAnimation] = []

    def configure_data_tree(
        self, tree: QTreeWidget, widths: list[int], settings_key: str
    ) -> None:
        """Apply one predictable, spreadsheet-like header behavior."""
        tree.setSortingEnabled(False)
        tree.setProperty("_alquimista_sort_column", -1)
        tree.setProperty(
            "_alquimista_sort_order", Qt.SortOrder.AscendingOrder.value
        )
        header = tree.header()
        header.setSectionsMovable(True)
        header.setSectionsClickable(True)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(70)
        header.setHighlightSections(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(True)
        for column, width in enumerate(widths):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.Interactive
            )
            tree.setColumnWidth(column, width)
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        if hasattr(header, "setSortIndicatorClearable"):
            header.setSortIndicatorClearable(False)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setAccessibleName("Tabela com colunas ordenáveis e reorganizáveis")
        if self.settings is not None:
            settings = self.settings
            saved = settings.value(f"tables/{settings_key}")
            if saved:
                header.restoreState(saved)
            header.sectionMoved.connect(
                lambda *_args: settings.setValue(
                    f"tables/{settings_key}", header.saveState()
                )
            )

            def resized(logical: int, _old: int, new: int) -> None:
                bounded = max(70, min(720, new))
                if bounded != new:
                    header.resizeSection(logical, bounded)
                settings.setValue(
                    f"tables/{settings_key}", header.saveState()
                )

            header.sectionResized.connect(resized)

        header.sectionClicked.connect(
            lambda column: self.sort_tree_by_column(tree, column)
        )

    def sort_tree_by_column(self, tree: QTreeWidget, column: int) -> None:
        """Sort ``tree`` by ``column``, toggling ascending/descending."""
        header = tree.header()
        current_section = tree.property("_alquimista_sort_column")
        current_order = tree.property("_alquimista_sort_order")
        if current_section == column:
            next_order = (
                Qt.SortOrder.DescendingOrder
                if current_order == Qt.SortOrder.AscendingOrder.value
                else Qt.SortOrder.AscendingOrder
            )
        else:
            next_order = Qt.SortOrder.AscendingOrder
        tree.setProperty("_alquimista_sort_column", column)
        tree.setProperty("_alquimista_sort_order", next_order.value)
        header.setSortIndicator(column, next_order)
        tree.sortItems(column, next_order)
        QTimer.singleShot(
            0,
            lambda: self.finalize_tree_sort(tree, column, next_order),
        )

    def finalize_tree_sort(
        self, tree: QTreeWidget, column: int, order: Qt.SortOrder
    ) -> None:
        """Keep the manual sort indicator after Qt finishes the click event."""
        if (
            tree.property("_alquimista_sort_column") != column
            or tree.property("_alquimista_sort_order") != order.value
        ):
            return
        tree.header().setSortIndicator(column, order)
        tree.sortItems(column, order)

    def restore_table_columns(
        self, tree: QTreeWidget, widths: list[int], settings_key: str
    ) -> None:
        header = tree.header()
        for logical in range(header.count()):
            visual = header.visualIndex(logical)
            if visual != logical:
                header.moveSection(visual, logical)
            tree.setColumnWidth(logical, widths[logical])
        if self.settings is not None:
            self.settings.remove(f"tables/{settings_key}")
        if self.status_bar is not None:
            self.status_bar.showMessage(
                translate_text("Organização padrão das colunas restaurada."),
                3500,
            )

    def move_page_column(
        self,
        column_choice: QComboBox,
        tree: QTreeWidget,
        direction: int,
    ) -> None:
        logical = column_choice.currentData()
        if logical is None:
            return
        header = tree.header()
        current = header.visualIndex(int(logical))
        target = max(0, min(header.count() - 1, current + direction))
        if target != current:
            header.moveSection(current, target)
            if self.status_bar is not None:
                self.status_bar.showMessage(
                    f"Coluna {column_choice.currentText()} movida para a posição {target + 1}.",
                    3500,
                )

    def send_page_column(
        self,
        column_choice: QComboBox,
        tree: QTreeWidget,
        to_end: bool,
    ) -> None:
        logical = column_choice.currentData()
        if logical is None:
            return
        header = tree.header()
        current = header.visualIndex(int(logical))
        target = header.count() - 1 if to_end else 0
        if target != current:
            header.moveSection(current, target)
            destination = "fim" if to_end else "início"
            if self.status_bar is not None:
                self.status_bar.showMessage(
                    f"Coluna {column_choice.currentText()} enviada para o {destination}.",
                    3500,
                )

    def reflow_space_cards(
        self,
        layout: QGridLayout,
        cards: dict[str, SourceCard],
        query: str,
        scroll_area: QScrollArea | None = None,
    ) -> None:
        """Repack matching cards into two rows inside the visible viewport."""
        if not cards:
            return
        for animation in self._space_card_animations:
            animation.stop()
        self._space_card_animations.clear()
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setVisible(False)
        matches = [
            card
            for card in cards.values()
            if not query
            or query in str(card.property("container_name") or "").casefold()
        ]
        for card_widget in cards.values():
            card_widget.setVisible(False)
        for index, card_widget in enumerate(matches):
            layout.addWidget(card_widget, index % 2, index // 2)
            card_widget.setVisible(True)
            card_widget.setEnabled(True)
        layout.activate()
        layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        if matches and scroll_area is not None:
            scroll_area.horizontalScrollBar().setValue(0)
            scroll_area.verticalScrollBar().setValue(0)
            scroll_area.ensureWidgetVisible(matches[0], 8, 8)

    @staticmethod
    def page_render_key(source_id: str, container_id: str) -> tuple[str, str]:
        return source_id, str(container_id)


__all__ = ["TreeController"]
