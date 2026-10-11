"""Output that stands on its own for AI tools (NotebookLM, Claude/ChatGPT projects)."""
from __future__ import annotations

from alquimista.markdown import KnowledgeDocumentRenderer, images_as_text
from alquimista.models import KnowledgeDocument, MarkdownOptions, ProjectConfig, SourceConfig, stable_json_hash


def test_images_become_text_without_authenticated_urls() -> None:
    markdown = (
        "Antes ![Fluxo de aprovação](https://wiki.example.com/download/attachments/1/fluxo.png?api=v2) depois\n"
        "![](https://wiki.example.com/download/attachments/1/tela%20inicial.png)\n"
        '[![logo](https://x.com/a.svg)](https://x.com)\n'
        '<img src="https://x.com/b/diagrama.jpg" alt="">'
    )

    text = images_as_text(markdown)

    assert "Antes [Imagem: Fluxo de aprovação] depois" in text
    assert "[Imagem: tela inicial.png]" in text
    assert "[Imagem: logo]" in text
    assert "[Imagem: diagrama.jpg]" in text
    assert "http" not in text


def test_image_reader_adds_the_text_found_in_the_image() -> None:
    read = {"https://x.com/fluxo.png": "Passo 1\n  Passo   2"}.get

    text = images_as_text("![Fluxo](https://x.com/fluxo.png) ![Outra](https://x.com/vazia.png)", read)

    assert text == "[Imagem: Fluxo — texto na imagem: Passo 1 Passo 2] [Imagem: Outra]"


def test_renderer_applies_the_option_and_new_projects_have_it_on() -> None:
    document = KnowledgeDocument(
        id="1", container_id="C", title="Página", content="![Mapa](https://x.com/mapa.png)", source_type="generic_web"
    )
    source = SourceConfig(id="s1", name="Fonte")

    assert ProjectConfig().markdown.images_as_text is True
    on = KnowledgeDocumentRenderer(MarkdownOptions()).prepare(document, source)
    off = KnowledgeDocumentRenderer(MarkdownOptions(images_as_text=False)).prepare(document, source)

    assert on.content == "[Imagem: Mapa]"
    assert off.content == "![Mapa](https://x.com/mapa.png)"


def test_existing_projects_keep_their_images_and_their_format_signature() -> None:
    old = ProjectConfig.from_dict({"schema_version": 4, "markdown": {"include_images": True}})

    assert old.markdown.images_as_text is False
    before_field = MarkdownOptions(images_as_text=False).model_dump()
    before_field.pop("images_as_text")
    assert MarkdownOptions(images_as_text=False).signature() == stable_json_hash(before_field)
