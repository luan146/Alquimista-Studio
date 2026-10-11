from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QScrollArea,
        QSplitter,
        QStyle,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidget,
        QVBoxLayout,
        QWidget,
)

from ..components import button, card, page_header
from ..dialogs.add_source_dialog import AddSourceDialog
from ..theme import current_colors
from .connection_page import build_connection_panel

STATE_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 40
_PILL_COLORS = {
        "success": ("success_soft", "success"),
        "warning": ("warning_soft", "warning"),
        "danger": ("danger_soft", "danger"),
        "neutral": ("surface_alt", "muted"),
}


class ConnectionPillDelegate(QStyledItemDelegate):
        """Paint the "Conexão" cell as a colored pill; the item keeps its text for code and tests."""

        @staticmethod
        def _font(option: QStyleOptionViewItem) -> QFont:
                font = QFont(option.font)
                font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
                font.setWeight(QFont.Weight.DemiBold)
                return font

        def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:
                width = QFontMetrics(self._font(option)).horizontalAdvance(str(index.data() or ""))
                return QSize(width + 32, super().sizeHint(option, index).height())

        def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: Any) -> None:
                view_option = QStyleOptionViewItem(option)
                self.initStyleOption(view_option, index)
                view_option.text = ""
                widget = view_option.widget
                style = widget.style() if widget is not None else None
                if style is not None:  # row background, hover and selection
                        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, view_option, painter, widget)
                text = str(index.data() or "")
                background, foreground = _PILL_COLORS.get(str(index.data(STATE_KIND_ROLE) or ""), _PILL_COLORS["neutral"])
                colors = current_colors()
                font = self._font(option)
                metrics = QFontMetrics(font)
                width = min(metrics.horizontalAdvance(text) + 20, option.rect.width() - 12)
                pill = QRect(option.rect.left() + 6, option.rect.center().y() - 11, max(0, width), 22)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(colors[background]))
                painter.drawRoundedRect(pill, 11, 11)
                painter.setFont(font)
                painter.setPen(QColor(colors[foreground]))
                elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(0, pill.width() - 16))
                painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, elided)
                painter.restore()


def build_sources_page(window: Any) -> QWidget:
        page, layout = page_header(
            "Fontes",
            "Adicione as fontes do projeto e conecte cada uma. Selecione uma fonte na lista para ver a conexão.",
            "📚",
        )
        # These controls remain as the internal compatibility form used by
        # connection/page workflows and by old project files. The visible page
        # below is intentionally a URL-first experience.
        legacy = QWidget(page)
        legacy.setVisible(False)
        window.sources_list = QListWidget(legacy)
        window.sources_list.currentRowChanged.connect(window._source_selected)
        window.src_name = QLineEdit(legacy)
        window.src_platform = QComboBox(legacy)
        for descriptor in window.connector_registry.all():
            label = f"{descriptor.display_name} — {descriptor.integration_name}"
            if descriptor.status_code.value == "experimental":
                label += " (Experimental)"
            elif not descriptor.runnable:
                label += " (Em desenvolvimento)"
            window.src_platform.addItem(label, descriptor.source_type)
            window.src_platform.setItemData(
                window.src_platform.count() - 1,
                not descriptor.runnable,
                Qt.ItemDataRole.UserRole + 1,
            )
            item = window.src_platform.model().item(window.src_platform.count() - 1)
            if item is not None:
                item.setEnabled(descriptor.runnable)
        window.src_platform.currentIndexChanged.connect(window._source_platform_changed)
        window.src_url = QLineEdit(legacy)
        window.src_url.setAccessibleName("URL da página do Confluence")
        window.src_space = QLineEdit(legacy)
        window.src_space_name = QLineEdit(legacy)
        window.src_root_mode = QComboBox(legacy)
        window.src_root_mode.addItem("Espaço inteiro", "space")
        window.src_root_mode.addItem("Pelo título (recomendado)", "title")
        window.src_root_mode.addItem("Pelo pageId (mais preciso)", "id")
        window.src_root_mode.currentIndexChanged.connect(window._source_root_mode_changed)
        window.src_root = QLineEdit(legacy)
        window.src_enabled = QCheckBox("Usar esta fonte nas execuções", legacy)
        window.src_include_root = QCheckBox("Incluir a própria página raiz", legacy)
        window.src_url_label = QLabel("URL da fonte", legacy)
        window.src_space_label = QLabel("Contêiner", legacy)
        window.src_space_name_label = QLabel("Nome do contêiner", legacy)
        window.src_autofill_status = QLabel(
            "A URL pode apontar para uma página, espaço, site ou raiz da plataforma.", legacy
        )

        toolbar = QHBoxLayout()
        window.add_source_button = button("＋ Adicionar fonte", window.open_add_source_dialog, primary=True)
        toolbar.addWidget(window.add_source_button)
        window.source_remove_button = button("🗑 Remover", window.remove_selected_sources, danger=True)
        toolbar.addWidget(window.source_remove_button)
        toolbar.addStretch()
        window.source_count_label = QLabel("0 itens")
        window.source_count_label.setObjectName("subtitle")
        toolbar.addWidget(window.source_count_label)
        window.sync_all_sources_button = button("🔄 Sincronizar Fontes", window.sync_project)
        window.sync_all_sources_button.setToolTip("Verificar e sincronizar alterações em todas as fontes ativas")
        toolbar.addWidget(window.sync_all_sources_button)
        layout.addLayout(toolbar)

        window.sources_split = QSplitter(Qt.Orientation.Horizontal)
        window.sources_split.setChildrenCollapsible(False)

        listing, listing_layout = card()
        listing_title = QLabel("Fontes do projeto")
        listing_title.setObjectName("sectionTitle")
        listing_layout.addWidget(listing_title)
        window.source_table = QTableWidget(0, 6)
        window.source_table.setHorizontalHeaderLabels(
            ["", "Nome da fonte", "URL", "Plataforma / API", "Conexão", ""]
        )
        window.source_table.setAccessibleName("Lista de fontes configuradas")
        window.source_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        window.source_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        window.source_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        window.source_table.verticalHeader().setVisible(False)
        window.source_table.verticalHeader().setDefaultSectionSize(40)
        window.source_table.setShowGrid(False)
        window.source_table.horizontalHeader().setStretchLastSection(False)
        source_header = window.source_table.horizontalHeader()
        # Name, URL and platform share the leftover width (and elide); the pill and the menu always fit.
        source_header.setMinimumSectionSize(36)
        for column, mode in enumerate((
                QHeaderView.ResizeMode.Fixed, QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.Stretch,
                QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                QHeaderView.ResizeMode.Fixed,
        )):
                source_header.setSectionResizeMode(column, mode)
        window.source_table.setWordWrap(False)
        window.source_table.setIconSize(QSize(20, 20))  # platform icon next to the name
        window.source_table.setItemDelegateForColumn(4, ConnectionPillDelegate(window.source_table))
        window.source_table.setColumnWidth(0, 36)
        window.source_table.setColumnWidth(5, 44)
        window.source_table.currentCellChanged.connect(
            lambda row, *_args: window._source_table_row_changed(row)
        )
        window.source_table.cellDoubleClicked.connect(
            lambda row, _column: window._edit_source_row(row)
        )
        listing_layout.addWidget(window.source_table, 1)

        window.sources_empty = QWidget()
        empty_layout = QVBoxLayout(window.sources_empty)
        empty_layout.addStretch()
        window.sources_empty_label = QLabel(
            "Adicione URLs de páginas para que o ALQuimista possa extrair e consolidar "
            "as informações automaticamente."
        )
        window.sources_empty_label.setObjectName("subtitle")
        window.sources_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        window.sources_empty_label.setWordWrap(True)
        empty_layout.addWidget(window.sources_empty_label)
        empty_layout.addWidget(
            button("＋ Adicionar a primeira fonte", window.open_add_source_dialog, primary=True),
            0,
            Qt.AlignmentFlag.AlignCenter,
        )
        empty_layout.addStretch()
        listing_layout.addWidget(window.sources_empty, 1)
        window.sources_split.addWidget(listing)

        window.connection_card = QScrollArea()
        window.connection_card.setWidgetResizable(True)
        window.connection_card.setFrameShape(QScrollArea.Shape.NoFrame)
        window.connection_card.setWidget(build_connection_panel(window))
        window.connection_card.setMinimumWidth(340)
        window.sources_split.addWidget(window.connection_card)
        window.sources_split.setStretchFactor(0, 3)
        window.sources_split.setStretchFactor(1, 2)
        layout.addWidget(window.sources_split, 1)

        window.add_source_dialog = AddSourceDialog(window)
        return page
