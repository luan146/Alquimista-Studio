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
        QTableWidget,
        QVBoxLayout,
        QWidget,
)

from ..components import button, card, page_header


def build_sources_page(window: Any) -> QWidget:
        page, layout = page_header(
            "Fontes de conteúdo",
            "Cole uma URL e o ALQuimista identifica a plataforma e prepara a conexão automaticamente.",
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

        entry, entry_layout = card()
        entry_title = QLabel("Adicionar uma fonte")
        entry_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        entry_layout.addWidget(entry_title)
        entry_row = QHBoxLayout()
        url_column = QVBoxLayout()
        url_column.addWidget(QLabel("URL da fonte"))
        window.source_url_input = QLineEdit()
        window.source_url_input.setPlaceholderText("Cole aqui a URL do Confluence, Notion, SharePoint, GitBook ou Zendesk")
        window.source_url_input.setAccessibleName("URL da fonte")
        window.source_url_input.textChanged.connect(window._preview_detected_source)
        url_column.addWidget(window.source_url_input)
        entry_row.addLayout(url_column, 3)
        name_column = QVBoxLayout()
        name_column.addWidget(QLabel("Nome da fonte (opcional)"))
        window.source_name_input = QLineEdit()
        window.source_name_input.setPlaceholderText("Nome da fonte")
        window.source_name_input.setAccessibleName("Nome opcional da fonte")
        name_column.addWidget(window.source_name_input)
        entry_row.addLayout(name_column, 1)
        entry_buttons = QVBoxLayout()
        window.source_add_button = button("＋ Adicionar", window._commit_source_from_form, primary=True)
        window.source_remove_button = button("🗑 Remover", window.remove_selected_sources, danger=True)
        window.source_cancel_button = button("Cancelar", window._cancel_source_edit)
        window.source_cancel_button.setEnabled(False)
        entry_buttons.addWidget(window.source_add_button)
        entry_buttons.addWidget(window.source_remove_button)
        entry_buttons.addWidget(window.source_cancel_button)
        entry_row.addLayout(entry_buttons)
        entry_layout.addLayout(entry_row)
        window.source_detection_status = QLabel(
            "A plataforma, a API e os detalhes iniciais serão identificados pela URL."
        )
        window.source_detection_status.setObjectName("subtitle")
        window.source_detection_status.setWordWrap(True)
        entry_layout.addWidget(window.source_detection_status)
        layout.addWidget(entry)

        listing, listing_layout = card()
        listing_header = QHBoxLayout()
        listing_title = QLabel("Lista de URLs")
        listing_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        listing_header.addWidget(listing_title)
        listing_header.addStretch()
        window.source_count_label = QLabel("0 itens")
        window.source_count_label.setObjectName("subtitle")
        listing_header.addWidget(window.source_count_label)
        listing_layout.addLayout(listing_header)
        window.source_table = QTableWidget(0, 6)
        window.source_table.setHorizontalHeaderLabels(
            ["", "URL", "Nome da fonte", "Plataforma / API", "Adicionado em", ""]
        )
        window.source_table.setAccessibleName("Lista de URLs de fontes configuradas")
        window.source_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        window.source_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        window.source_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        window.source_table.verticalHeader().setVisible(False)
        window.source_table.horizontalHeader().setStretchLastSection(False)
        source_header = window.source_table.horizontalHeader()
        source_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        source_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        source_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
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
        window.sources_empty_label = QLabel(
            "Adicione URLs de páginas para que o ALQuimista possa extrair e consolidar "
            "as informações automaticamente."
        )
        window.sources_empty_label.setObjectName("subtitle")
        window.sources_empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        window.sources_empty_label.setWordWrap(True)
        listing_layout.addWidget(window.sources_empty_label)
        layout.addWidget(listing, 1)
        return page


