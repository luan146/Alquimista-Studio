from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
        QAbstractItemView,
        QCheckBox,
        QComboBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QSplitter,
        QTableWidget,
        QVBoxLayout,
        QWidget,
)

from ..components import button, card, page_header
from ..dialogs.add_source_dialog import AddSourceDialog
from .connection_page import build_connection_panel


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
        listing_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
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
        window.source_table.horizontalHeader().setStretchLastSection(False)
        source_header = window.source_table.horizontalHeader()
        source_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        source_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        window.source_table.setWordWrap(False)
        source_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        source_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        window.source_table.setColumnWidth(0, 42)
        window.source_table.setColumnWidth(5, 52)
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

        window.connection_card = build_connection_panel(window)
        window.sources_split.addWidget(window.connection_card)
        window.sources_split.setStretchFactor(0, 3)
        window.sources_split.setStretchFactor(1, 2)
        layout.addWidget(window.sources_split, 1)

        window.add_source_dialog = AddSourceDialog(window)
        return page
