from __future__ import annotations

from functools import partial
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from ..components import SegmentedControl, VisibilityBadgeDelegate, button, chip, page_header, section_title
from ..space_cards import SpaceCardDelegate


def _ghost(text: str, slot: Any, tooltip: str) -> Any:
    result = button(text, slot)
    result.setProperty("ghost", True)
    result.setToolTip(tooltip)
    result.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return result


def build_selection_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Seleção do conhecimento",
        "Marque um espaço inteiro ou abra-o para escolher páginas.",
        "☑",
    )
    window._active_selection_container = None
    window._selection_container_cards = {}

    source_tools = QHBoxLayout()
    window.selection_source = QComboBox()
    window.selection_source.setAccessibleName("Fonte")
    window.selection_source.currentIndexChanged.connect(window._selection_source_changed)
    source_tools.addWidget(window.selection_source, 1)
    window.selection_load_button = button("🌳 Carregar espaços", window.load_tree, primary=True)
    source_tools.addWidget(window.selection_load_button)
    window.selection_cancel_button = button("Cancelar", window._cancel_tree_operation, danger=True)
    window.selection_cancel_button.setEnabled(False)
    source_tools.addWidget(window.selection_cancel_button)
    layout.addLayout(source_tools)

    window.selection_stack = QStackedWidget()

    home = QWidget()
    home_layout = QVBoxLayout(home)
    home_layout.setContentsMargins(0, 4, 0, 0)
    window.selection_home_layout = home_layout
    home_top = QHBoxLayout()
    window.selection_space_search = QLineEdit()
    window.selection_space_search.setObjectName("searchField")
    window.selection_space_search.setPlaceholderText("Pesquisar espaço…")
    window.selection_space_search.setClearButtonEnabled(True)
    window.selection_space_search.textChanged.connect(window._filter_selection_space_cards)
    home_top.addWidget(window.selection_space_search, 1)
    window.selection_total = chip("", "accent")
    home_top.addWidget(window.selection_total)
    home_layout.addLayout(home_top)
    window.selection_home_empty = QLabel(
        "Carregue os espaços da fonte para escolher o que extrair."
    )
    window.selection_home_empty.setObjectName("subtitle")
    window.selection_home_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.selection_home_empty.setWordWrap(True)
    home_layout.addWidget(window.selection_home_empty, 1)
    window.selection_spaces = QListWidget()
    window.selection_spaces.setObjectName("spaceCards")
    window.selection_spaces.setAccessibleName("Espaços da fonte")
    window.selection_spaces.setViewMode(QListView.ViewMode.IconMode)
    window.selection_spaces.setResizeMode(QListView.ResizeMode.Adjust)
    window.selection_spaces.setMovement(QListView.Movement.Static)
    window.selection_spaces.setUniformItemSizes(True)
    window.selection_spaces.setSpacing(4)
    window.selection_spaces.setSelectionMode(QListWidget.SelectionMode.NoSelection)
    window.selection_spaces.setMouseTracking(True)
    window.selection_spaces.setToolTip(
        "Clique em “Inteiro” para levar o espaço todo, ou no cartão para escolher páginas."
    )
    delegate = SpaceCardDelegate(window.selection_spaces)
    delegate.whole_toggled.connect(window._mark_whole_space)
    delegate.open_requested.connect(window._open_selection_container)
    window.selection_spaces.setItemDelegate(delegate)
    window.selection_space_delegate = delegate
    window.selection_spaces.itemActivated.connect(
        lambda item: window._open_selection_container(str(item.data(Qt.ItemDataRole.UserRole)))
    )
    window.selection_spaces.setVisible(False)
    home_layout.addWidget(window.selection_spaces, 1)
    window.selection_stack.addWidget(home)

    detail = QWidget()
    detail_layout = QVBoxLayout(detail)
    detail_layout.setContentsMargins(0, 4, 0, 0)
    crumbs = QHBoxLayout()
    window.selection_back_button = button("Espaços", window._selection_go_back)
    window.selection_back_button.setProperty("ghost", True)
    window.selection_back_button.setToolTip("Voltar para a lista de espaços")
    window.selection_back_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    crumbs.addWidget(window.selection_back_button)
    separator = QLabel("›")
    separator.setObjectName("subtitle")
    crumbs.addWidget(separator)
    window.selection_space_title = section_title("Espaço selecionado")
    crumbs.addWidget(window.selection_space_title)
    crumbs.addStretch()
    window.selection_count = chip("0 páginas selecionadas", "accent")
    crumbs.addWidget(window.selection_count)
    detail_layout.addLayout(crumbs)

    tools = QHBoxLayout()
    window.selection_search = QLineEdit()
    window.selection_search.setObjectName("searchField")
    window.selection_search.setPlaceholderText("Pesquisar por título, caminho ou pageId…")
    window.selection_search.setClearButtonEnabled(True)
    window.selection_search.textChanged.connect(window._filter_selection)
    tools.addWidget(window.selection_search, 1)
    window.selection_filter = QComboBox()
    for label, value in [
        ("📋 Todas as páginas", "all"),
        ("✅ Somente selecionadas", "selected"),
        ("⬜ Somente não selecionadas", "unselected"),
        ("🌐 Páginas públicas", "public"),
        ("🔒 Páginas privadas", "private"),
        ("❓ Páginas desconhecidas", "unknown"),
    ]:
        window.selection_filter.addItem(label, value)
    window.selection_filter.currentIndexChanged.connect(window._filter_selection)
    window.selection_filter.setVisible(False)
    tools.addWidget(window.selection_filter)
    window.selection_filter_pills = SegmentedControl(
        [("Todas", "all"), ("Marcadas", "selected"), ("Não marcadas", "unselected")]
    ).bind_combo(window.selection_filter)
    tools.addWidget(window.selection_filter_pills)
    detail_layout.addLayout(tools)

    actions = QHBoxLayout()
    actions.setSpacing(4)
    actions.addWidget(_ghost(
        "Marcar tudo",
        lambda _checked=False: window._set_selection(Qt.CheckState.Checked, visible_only=False),
        "Marca todas as páginas do espaço.",
    ))
    actions.addWidget(_ghost(
        "Desmarcar tudo",
        lambda _checked=False: window._set_selection(Qt.CheckState.Unchecked, visible_only=False),
        "Desmarca todas as páginas do espaço.",
    ))
    actions.addWidget(_ghost("Inverter", window._invert_selection, "Inverte a seleção atual."))
    more_button = QToolButton()
    more_button.setText("Mais ▾")
    more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    more_menu = QMenu(more_button)
    more_menu.addAction("Expandir tudo", lambda: window.selection_tree.expandAll())
    more_menu.addAction("Recolher tudo", lambda: window.selection_tree.collapseAll())
    more_menu.addAction("Mostrar/ocultar caminho", lambda: window.selection_tree.setColumnHidden(
        2, not window.selection_tree.isColumnHidden(2)))
    more_menu.addAction("Mostrar/ocultar Page ID", window._toggle_page_id_column)
    more_menu.addSeparator()

    def show_only(value: str) -> None:
        window.selection_filter.setCurrentIndex(window.selection_filter.findData(value))

    for label, value in (("Só páginas públicas", "public"), ("Só páginas restritas", "private"),
                         ("Só acesso desconhecido", "unknown")):
        more_menu.addAction(label, partial(show_only, value))
    more_menu.addSeparator()
    more_menu.addAction("Sincronizar seleção", lambda: window.sync_selection())
    more_button.setMenu(more_menu)
    actions.addWidget(more_button)
    actions.addStretch()
    detail_layout.addLayout(actions)

    window.selection_tree = QTreeWidget()
    window.selection_tree.setColumnCount(5)
    window.selection_tree.setHeaderLabels(["Página", "Page ID", "Caminho", "Atualização", "Estado"])
    window._configure_data_tree(window.selection_tree, [360, 120, 420, 140, 150], "selection")
    window.selection_tree.setItemDelegateForColumn(0, VisibilityBadgeDelegate(window.selection_tree))
    window.selection_tree.itemExpanded.connect(window._selection_tree_item_expanded)
    window.selection_tree.itemChanged.connect(window._selection_changed)
    window.selection_tree.header().setStretchLastSection(True)  # no grey block after "Estado"
    window.selection_tree.setColumnHidden(1, True)
    window.selection_tree.setColumnHidden(2, True)  # the tree already shows where a page lives
    window.selection_tree.setAlternatingRowColors(False)
    window.selection_tree.setToolTip("Clique duas vezes numa página para ver o Markdown dela.")
    window.selection_tree.itemDoubleClicked.connect(window._selection_item_double_clicked)
    window.selection_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    window.selection_tree.customContextMenuRequested.connect(window._selection_context_menu)
    detail_layout.addWidget(window.selection_tree, 1)
    footer = QHBoxLayout()
    window.selection_render_status = QLabel("Nenhum espaço carregado")
    window.selection_render_status.setObjectName("subtitle")
    footer.addWidget(window.selection_render_status, 1)
    window.selection_load_more_button = button(
        "🌳 Carregar mais páginas", window._load_more_selection_rows, primary=True
    )
    window.selection_load_more_button.setVisible(False)
    footer.addWidget(window.selection_load_more_button)
    detail_layout.addLayout(footer)
    window.selection_stack.addWidget(detail)
    layout.addWidget(window.selection_stack, 1)
    return page
