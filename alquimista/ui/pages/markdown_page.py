from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..components import CollapsibleSection, SegmentedControl, button, card, chip, page_header, section_title
from ..icons import svg_icon


class OptionRow(QFrame):
    """Name and help on the left, a switch on the right; clicking anywhere on the row toggles it."""

    def __init__(self, check: QCheckBox, label: str, help_text: str) -> None:
        super().__init__()
        self.setObjectName("optionRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check = check
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 6, 4, 6)
        text = QVBoxLayout()
        text.setSpacing(0)
        title = QLabel(label)
        title.setObjectName("optionTitle")
        description = QLabel(help_text)
        description.setObjectName("subtitle")
        description.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(description)
        row.addLayout(text, 1)
        check.setProperty("switch", True)
        check.setAccessibleName(label)
        check.setToolTip(help_text)
        row.addWidget(check)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._check.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)


def build_markdown_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Personalização do Markdown",
        "Escolha o que entra nos documentos. A prévia mostra somente o arquivo que será gerado.",
        "✍",
    )

    window.preset_cards = {}
    preset_group = QButtonGroup(page)
    preset_row = QHBoxLayout()
    preset_row.setSpacing(10)
    for title, detail, icon_name, name in [
        ("Mínimo", "Só o texto", "pagina", "minimum"),
        ("Recomendado", "Equilíbrio", "selecao", "recommended"),
        ("Rastreável", "Origem e datas", "chave", "traceability"),
        ("Para IA", "Pronto para RAG", "fontes", "rag"),
    ]:
        preset = QToolButton()
        preset.setObjectName("presetCard")
        preset.setText(f"{title}\n{detail}")
        preset.setIcon(svg_icon(icon_name, 28))
        preset.setIconSize(QSize(28, 28))
        preset.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        preset.setCheckable(True)
        preset.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        preset.setMinimumHeight(56)
        preset.clicked.connect(lambda _checked=False, value=name: window._apply_preset(value))
        preset_group.addButton(preset)
        window.preset_cards[name] = preset
        preset_row.addWidget(preset)
    layout.addLayout(preset_row)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    options_scroll = QScrollArea()
    options_scroll.setWidgetResizable(True)
    options_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    options_widget = QWidget()
    options_layout = QVBoxLayout(options_widget)
    options_layout.setContentsMargins(0, 0, 8, 0)
    options_layout.setSpacing(10)

    options_card, options_card_layout = card()
    options_card_layout.setContentsMargins(16, 16, 16, 16)
    options_title = QLabel("O que incluir no arquivo")
    options_title.setObjectName("sectionTitle")
    options_subtitle = QLabel("Marque as opções para compor o conteúdo do Markdown.")
    options_subtitle.setObjectName("subtitle")
    options_subtitle.setWordWrap(True)
    options_card_layout.addWidget(options_title)
    options_card_layout.addWidget(options_subtitle)
    expand_all = button("Expandir todos", lambda: window._set_markdown_sections(True))
    expand_all.setObjectName("markdownTextButton")
    collapse_all = button("Recolher todos", lambda: window._set_markdown_sections(False))
    collapse_all.setObjectName("markdownTextButton")
    sections_row = QHBoxLayout()  # own row: beside the title it overflowed narrow windows
    sections_row.addStretch()
    sections_row.addWidget(expand_all)
    sections_row.addWidget(collapse_all)
    options_card_layout.addLayout(sections_row)

    window.md_controls = {}
    window.markdown_sections = []

    def option_row(key: str, label: str, help_text: str) -> QFrame:
        check = QCheckBox()
        window.md_controls[key] = check
        return OptionRow(check, label, help_text)

    def section(
        title: str,
        icon: str,
        items: list[tuple[str, str, str]],
        *,
        expanded: bool,
    ) -> CollapsibleSection:
        current = CollapsibleSection(title, icon, expanded=expanded)
        for key, label, help_text in items:
            current.addWidget(option_row(key, label, help_text))
        window.markdown_sections.append(current)
        options_card_layout.addWidget(current)
        return current

    section(
        "Estrutura e identificação",
        "▣",
        [
            ("include_title", "Título", "Identifica o assunto da página."),
            ("include_source_url", "URL original", "Cria um link clicável para a origem."),
            ("include_module", "Módulo", "Primeiro agrupamento abaixo da raiz."),
            ("include_path", "Caminho", "Trilha hierárquica completa."),
            ("include_updated_at", "Atualização", "Data da última versão."),
            ("include_hash", "SHA-256", "Detecta mudanças e duplicidade exata."),
        ],
        expanded=True,
    )
    section(
        "Conteúdo principal",
        "▤",
        [
            ("include_images", "Imagens", "Preserva referências visuais."),
            ("include_image_alt_text", "Texto alternativo", "Melhora acessibilidade e contexto."),
            (
                "images_as_text",
                "Imagens como texto (para IA)",
                "Troca cada imagem por uma descrição e pelo texto lido nela; IA não abre imagens que exigem login.",
            ),
            ("include_attachments", "Anexos", "Converte anexos em links."),
            ("include_videos", "Vídeos", "Preserva referências de vídeo."),
            ("include_links", "Links", "Mantém links clicáveis."),
            ("include_tables", "Tabelas", "Converte tabelas para Markdown."),
            ("include_code_blocks", "Blocos de código", "Preserva exemplos técnicos."),
            ("include_panels", "Avisos e dicas", "Transforma painéis do Confluence."),
            ("include_expand_macros", "Macros expand", "Inclui conteúdo recolhível."),
            ("include_content_macros", "Outras macros", "Aplica fallback legível."),
            ("include_empty_pages", "Páginas vazias", "Mantém páginas sem conteúdo técnico."),
        ],
        expanded=True,
    )

    metadata_section = CollapsibleSection("Metadados complementares", "▤", expanded=False)
    metadata_form = QFormLayout()
    metadata_form.setContentsMargins(2, 4, 2, 4)
    metadata_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
    metadata_style = QComboBox()
    for label, value in [
        ("Informações em Markdown — recomendado", "markdown"),
        ("Cabeçalho YAML", "yaml"),
        ("Markdown e YAML", "both"),
        ("Sem metadados", "none"),
    ]:
        metadata_style.addItem(label, value)
    window.md_controls["metadata_style"] = metadata_style
    heading = QSpinBox()
    heading.setRange(1, 6)
    window.md_controls["title_heading_level"] = heading
    hash_scope = QComboBox()
    for label, value in [
        ("Somente o conteúdo", "content"),
        ("Título e conteúdo — recomendado", "title_content"),
        ("Título, conteúdo e informações estáveis", "stable_metadata"),
    ]:
        hash_scope.addItem(label, value)
    window.md_controls["hash_scope"] = hash_scope
    for combo in (metadata_style, hash_scope):  # long texts must not widen the options column
        combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(12)
    content_heading = QCheckBox("Adicionar título ‘Conteúdo técnico’")
    content_heading.setProperty("switch", True)
    content_heading.setToolTip("Separa os metadados do texto convertido da página.")
    window.md_controls["include_content_heading"] = content_heading
    metadata_form.addRow("Formato dos metadados", metadata_style)
    metadata_form.addRow("Nível do título", heading)
    metadata_form.addRow("Escopo do SHA-256", hash_scope)
    metadata_form.addRow("Organização do conteúdo", content_heading)
    metadata_section.addLayout(metadata_form)
    window.markdown_sections.append(metadata_section)
    options_card_layout.addWidget(metadata_section)

    section(
        "Organização do arquivo",
        "▰",
        [
            ("absolute_links", "Links absolutos", "Converte caminhos relativos."),
            ("normalize_spaces", "Normalizar espaços", "Padroniza quebras e espaços."),
            ("remove_noise", "Remover ruído", "Remove navegação, scripts e elementos auxiliares."),
            ("remove_html_comments", "Remover comentários", "Descarta comentários HTML."),
        ],
        expanded=False,
    )
    options_card_layout.addStretch()
    options_layout.addWidget(options_card)
    options_layout.addStretch()
    options_scroll.setWidget(options_widget)
    splitter.addWidget(options_scroll)

    preview_card, preview_layout = card()
    preview_card.setObjectName("markdownPreviewCard")
    preview_header = QHBoxLayout()
    preview_header.addWidget(section_title("Arquivo gerado"))
    preview_header.addWidget(chip("● Prévia ao vivo", "success"))
    preview_header.addStretch()
    window.preview_mode = QComboBox()
    window.preview_mode.addItem("Visualização de leitura", "reading")
    window.preview_mode.addItem("Código Markdown", "code")
    window.preview_mode.currentIndexChanged.connect(window._render_preview_mode)
    window.preview_mode.setVisible(False)
    window.preview_mode_pills = SegmentedControl([("Visual", "reading"), ("Código", "code")]).bind_combo(
        window.preview_mode
    )
    preview_header.addWidget(window.preview_mode)
    preview_header.addWidget(window.preview_mode_pills)
    preview_layout.addLayout(preview_header)
    window.preview_source_row = QHBoxLayout()
    window.preview_source_label = QLabel(
        "Página de exemplo. Para ver uma página sua, clique duas vezes nela em Seleção."
    )
    window.preview_source_label.setObjectName("subtitle")
    window.preview_source_label.setWordWrap(True)
    window.preview_source_row.addWidget(window.preview_source_label, 1)
    window.preview_sample_button = button("Usar exemplo", window._clear_real_preview)
    window.preview_sample_button.setVisible(False)
    window.preview_source_row.addWidget(window.preview_sample_button)
    preview_layout.addLayout(window.preview_source_row)
    window.preview_after = QTextEdit()
    window.preview_after.setObjectName("markdownPreview")
    window.preview_after.setReadOnly(True)
    window.preview_after.setPlaceholderText("A prévia do arquivo aparecerá aqui.")
    preview_layout.addWidget(window.preview_after, 1)
    splitter.addWidget(preview_card)
    splitter.setSizes([610, 720])
    layout.addWidget(splitter, 1)

    window.preview_timer = QTimer(window)
    window.preview_timer.setSingleShot(True)
    window.preview_timer.setInterval(250)
    window.preview_timer.timeout.connect(window._update_preview)
    window._preview_after_raw = ""
    for control in window.md_controls.values():
        if isinstance(control, QCheckBox):
            control.toggled.connect(window._schedule_preview)
        elif isinstance(control, QComboBox):
            control.currentTextChanged.connect(window._schedule_preview)
        elif isinstance(control, QSpinBox):
            control.valueChanged.connect(window._schedule_preview)
        elif isinstance(control, QLineEdit):
            control.textChanged.connect(window._schedule_preview)
    return page

