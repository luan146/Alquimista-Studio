from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ..components import (
    FlowLayout,
    HorizontalScrollArea,
    VisibilityBadgeDelegate,
    button,
    page_header,
)


def build_selection_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Seleção do conhecimento",
        "Escolha um espaço/container e depois marque as pastas e páginas que deseja extrair.",
        "☑",
    )
    window._active_selection_container = None
    window._selection_container_cards = {}

    source_tools = QHBoxLayout()
    source_tools.addWidget(QLabel("Fonte"))
    window.selection_source = QComboBox()
    window.selection_source.currentIndexChanged.connect(window._selection_source_changed)
    source_tools.addWidget(window.selection_source, 1)
    window.selection_load_button = button("🌳 Carregar espaços", window.load_tree, primary=True)
    source_tools.addWidget(window.selection_load_button)
    window.selection_cancel_button = button(
        "Cancelar", window._cancel_tree_operation, danger=True
    )
    window.selection_cancel_button.setEnabled(False)
    source_tools.addWidget(window.selection_cancel_button)
    layout.addLayout(source_tools)

    window.selection_stack = QStackedWidget()

    home = QWidget()
    home_layout = QVBoxLayout(home)
    home_layout.setContentsMargins(0, 4, 0, 0)
    window.selection_home_layout = home_layout
    window.selection_home_empty = QLabel(
        "🌳 Carregue a árvore da fonte para visualizar os espaços e containers disponíveis."
    )
    window.selection_home_empty.setObjectName("subtitle")
    window.selection_home_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.selection_home_empty.setWordWrap(True)
    home_layout.addWidget(window.selection_home_empty, 1)
    window.selection_space_search = QLineEdit()
    window.selection_space_search.setPlaceholderText("🔎 Pesquisar por nome do espaço…")
    window.selection_space_search.setClearButtonEnabled(True)
    window.selection_space_search.textChanged.connect(window._filter_selection_space_cards)
    home_layout.addWidget(window.selection_space_search)
    window.selection_cards_scroll = HorizontalScrollArea()
    window.selection_cards_scroll.setObjectName("spaceCardsScroll")
    window.selection_cards_scroll.setWidgetResizable(True)
    window.selection_cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
    window.selection_cards_scroll.setHorizontalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    window.selection_cards_scroll.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAsNeeded
    )
    selection_cards_host = QWidget()
    window.selection_cards_layout = QGridLayout(selection_cards_host)
    window.selection_cards_layout.setContentsMargins(8, 12, 8, 16)
    window.selection_cards_layout.setHorizontalSpacing(16)
    window.selection_cards_layout.setVerticalSpacing(16)
    window.selection_cards_scroll.setWidget(selection_cards_host)
    home_layout.addWidget(window.selection_cards_scroll, 1)
    window.selection_cards_scroll.setVisible(False)
    window.selection_stack.addWidget(home)

    detail = QWidget()
    detail_layout = QVBoxLayout(detail)
    detail_layout.setContentsMargins(0, 4, 0, 0)
    detail_tools = QHBoxLayout()
    window.selection_back_button = button("← Voltar", window._selection_go_back)
    window.selection_back_button.setMaximumWidth(180)
    window.selection_back_button.setMinimumWidth(120)
    detail_tools.addWidget(window.selection_back_button)
    window.selection_space_title = QLabel("Espaço selecionado")
    window.selection_space_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
    detail_tools.addWidget(window.selection_space_title)
    detail_tools.addStretch()
    detail_layout.addLayout(detail_tools)

    controls = QVBoxLayout()
    controls.setContentsMargins(0, 0, 0, 0)
    controls.setSpacing(8)

    search_row = QHBoxLayout()
    window.selection_search = QLineEdit()
    window.selection_search.setPlaceholderText("🔎 Pesquisar por título, caminho ou pageId…")
    window.selection_search.textChanged.connect(window._filter_selection)
    search_row.addWidget(window.selection_search, 1)
    window.selection_filter = QComboBox()
    window.selection_filter.addItem("📋 Todas as páginas", "all")
    window.selection_filter.addItem("✅ Somente selecionadas", "selected")
    window.selection_filter.addItem("⬜ Somente não selecionadas", "unselected")
    window.selection_filter.addItem("🌐 Páginas públicas", "public")
    window.selection_filter.addItem("🔒 Páginas privadas", "private")
    window.selection_filter.addItem("❓ Páginas desconhecidas", "unknown")
    window.selection_filter.currentIndexChanged.connect(window._filter_selection)
    search_row.addWidget(window.selection_filter)
    controls.addLayout(search_row)

    def selection_button(text: str, slot: Any, tooltip: str) -> Any:
        result = button(text, slot)
        result.setToolTip(tooltip)
        return result

    selection_actions = FlowLayout(spacing=6)
    selection_actions.addWidget(
        selection_button(
            "Marcar tudo",
            lambda _checked=False: window._set_selection(Qt.CheckState.Checked, visible_only=False),
            "Marca todas as páginas do espaço.",
        )
    )
    selection_actions.addWidget(
        selection_button(
            "Desmarcar tudo",
            lambda _checked=False: window._set_selection(Qt.CheckState.Unchecked, visible_only=False),
            "Desmarca todas as páginas do espaço.",
        )
    )
    selection_actions.addWidget(
        selection_button("Inverter seleção", window._invert_selection, "Inverte a seleção atual.")
    )
    selection_actions.addWidget(
        button(
            "📂 Expandir tudo",
            lambda: window.selection_tree.expandAll(),
        )
    )
    selection_actions.addWidget(
        button(
            "📁 Recolher tudo",
            lambda: window.selection_tree.collapseAll(),
        )
    )
    selection_actions.addWidget(
        selection_button(
            "🔄 Sincronizar seleção",
            lambda _checked=False: window.sync_selection(),
            "Verifica e sincroniza incrementalmente apenas as páginas selecionadas.",
        )
    )
    controls.addLayout(selection_actions)
    detail_layout.addLayout(controls)


    window.selection_tree = QTreeWidget()
    window.selection_tree.setColumnCount(5)
    window.selection_tree.setHeaderLabels(["Página", "Page ID", "Caminho", "Atualização", "Estado"])
    window._configure_data_tree(
        window.selection_tree, [310, 120, 480, 210, 150], "selection"
    )
    window.selection_tree.setItemDelegateForColumn(0, VisibilityBadgeDelegate(window.selection_tree))
    window.selection_tree.itemExpanded.connect(window._selection_tree_item_expanded)
    window.selection_tree.itemChanged.connect(window._selection_changed)
    detail_layout.addWidget(window.selection_tree, 1)
    selection_render_tools = QHBoxLayout()
    window.selection_render_status = QLabel("Nenhum espaço carregado")
    window.selection_render_status.setObjectName("subtitle")
    selection_render_tools.addWidget(window.selection_render_status, 1)
    window.selection_load_more_button = button(
        "🌳 Carregar mais páginas", window._load_more_selection_rows, primary=True
    )
    window.selection_load_more_button.setVisible(False)
    selection_render_tools.addWidget(window.selection_load_more_button)
    detail_layout.addLayout(selection_render_tools)
    guidance = QLabel(
        "💡 As pastas organizam a árvore. As seleções ficam preservadas quando você volta "
        "aos espaços ou abre outro container."
    )
    guidance.setObjectName("subtitle")
    guidance.setWordWrap(True)
    detail_layout.addWidget(guidance)
    window.selection_count = QLabel("0 páginas selecionadas")
    window.selection_count.setStyleSheet("font-weight: 600;")
    detail_layout.addWidget(window.selection_count)
    window.selection_stack.addWidget(detail)
    layout.addWidget(window.selection_stack, 1)
    return page
