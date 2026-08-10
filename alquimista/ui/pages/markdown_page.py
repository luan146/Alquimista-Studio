from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import CollapsibleSection, button, card, page_header


def build_markdown_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Personalização do Markdown",
        "Escolha o que entra nos documentos. A prévia mostra somente o arquivo que será gerado.",
        "✍",
    )

    beginner = QLabel(
        "💡 Markdown preserva a estrutura do conteúdo: títulos, listas e links são "
        "convertidos automaticamente. A URL original continua disponível na estrutura de identificação."
    )
    beginner.setWordWrap(True)
    beginner.setObjectName("subtitle")
    layout.addWidget(beginner)

    preset_row = QHBoxLayout()
    for label, name in [
        ("🌱 Mínimo", "minimum"),
        ("⭐ Recomendado", "recommended"),
        ("🔎 Rastreabilidade", "traceability"),
        ("🧠 Preparado para RAG", "rag"),
    ]:
        preset_row.addWidget(
            button(label, lambda _checked=False, value=name: window._apply_preset(value))
        )
    preset_row.addStretch()
    preset_row.addWidget(button("↺ Restaurar padrões", lambda: window._apply_preset("recommended")))
    layout.addLayout(preset_row)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    options_scroll = QScrollArea()
    options_scroll.setWidgetResizable(True)
    options_widget = QWidget()
    options_layout = QVBoxLayout(options_widget)
    options_layout.setContentsMargins(0, 0, 8, 0)
    options_layout.setSpacing(10)

    options_card, options_card_layout = card()
    options_card_layout.setContentsMargins(16, 16, 16, 16)
    options_heading = QHBoxLayout()
    heading_text = QVBoxLayout()
    options_title = QLabel("O que incluir no arquivo")
    options_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
    options_subtitle = QLabel("Marque as opções para compor o conteúdo do Markdown.")
    options_subtitle.setObjectName("subtitle")
    heading_text.addWidget(options_title)
    heading_text.addWidget(options_subtitle)
    options_heading.addLayout(heading_text, 1)
    expand_all = button("Expandir todos", lambda: window._set_markdown_sections(True))
    expand_all.setObjectName("markdownTextButton")
    collapse_all = button("Recolher todos", lambda: window._set_markdown_sections(False))
    collapse_all.setObjectName("markdownTextButton")
    options_heading.addWidget(expand_all)
    options_heading.addWidget(collapse_all)
    options_card_layout.addLayout(options_heading)

    window.md_controls = {}
    window.markdown_sections = []

    def option_row(key: str, label: str, help_text: str) -> QFrame:
        row = QFrame()
        row.setObjectName("markdownOptionRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 4, 2, 4)
        row_layout.setSpacing(10)
        check = QCheckBox(label)
        check.setToolTip(help_text)
        window.md_controls[key] = check
        row_layout.addWidget(check)
        description = QLabel(help_text)
        description.setObjectName("subtitle")
        description.setWordWrap(True)
        row_layout.addWidget(description, 1)
        return row

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
    content_heading = QCheckBox("Adicionar título ‘Conteúdo técnico’")
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
    preview_title = QLabel("📄 Arquivo gerado")
    preview_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
    preview_header.addWidget(preview_title)
    preview_header.addStretch()
    preview_status = QLabel("● Prévia ao vivo")
    preview_status.setObjectName("markdownPreviewStatus")
    preview_header.addWidget(preview_status)
    preview_layout.addLayout(preview_header)
    preview_subtitle = QLabel("Prévia ao vivo do Markdown com as opções selecionadas.")
    preview_subtitle.setObjectName("subtitle")
    preview_layout.addWidget(preview_subtitle)
    preview_mode_row = QHBoxLayout()
    preview_mode_row.addWidget(QLabel("Mostrar como"))
    window.preview_mode = QComboBox()
    window.preview_mode.addItem("Código Markdown", "code")
    window.preview_mode.addItem("Visualização de leitura", "reading")
    window.preview_mode.currentIndexChanged.connect(window._render_preview_mode)
    preview_mode_row.addWidget(window.preview_mode, 1)
    preview_layout.addLayout(preview_mode_row)
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

