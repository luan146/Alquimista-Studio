from __future__ import annotations

from alquimista.markdown import (
    MarkdownTransformer,
    format_updated_at,
    knowledge_document_metadata,
    page_metadata,
    sample_page,
    sha256_text,
)
from alquimista.models import KnowledgeDocument, MarkdownOptions, SourceConfig


class Client:
    base_url = "https://example.test"


def test_updated_at_uses_brazilian_date_and_time_format() -> None:
    assert format_updated_at("2020-06-18T21:04:38.517-03:00") == "18/06/2020 21:04"


def transformer(**options):
    source = SourceConfig(
        id="s1",
        name="Fonte",
        base_url="https://example.test",
        space_key="DOC",
    )
    root = {"id": "100", "title": "Manual", "space": {"key": "DOC"}}
    return MarkdownTransformer(Client(), source, root, MarkdownOptions(**options)), source, root


def test_hash_is_deterministic_and_normalizes_line_endings() -> None:
    assert sha256_text("ação\r\n") == sha256_text("ação\n")


def test_panels_links_and_utf8_are_readable() -> None:
    instance, _source, _root = transformer()
    page = sample_page()
    page["body"]["storage"]["value"] += (
        "<ac:link><ri:page ri:content-title='Configuração'/>"
        "<ac:plain-text-link-body>abrir configuração</ac:plain-text-link-body></ac:link>"
    )
    text = instance.technical_markdown(page)
    assert "💡 Dica" in text
    assert "abrir configuração" in text
    assert "https://example.test" in text


def test_relative_urls_become_absolute() -> None:
    instance, _source, _root = transformer()
    page = sample_page()
    page["body"]["storage"]["value"] = '<p><a href="/display/DOC/Teste">Teste</a></p>'
    assert "(https://example.test/display/DOC/Teste)" in instance.technical_markdown(page)


def test_hash_scope_excludes_collection_date() -> None:
    instance, source, root = transformer(hash_scope="stable_metadata")
    page = sample_page()
    meta = page_metadata(page, source, root)
    value = instance.hash_input(meta, "conteúdo")
    assert "2026-07-26T15:00:00-03:00" not in value


def test_knowledge_document_metadata_normalizes_ancestors() -> None:
    source = SourceConfig(id="s1", name="Fonte", base_url="https://example.test")
    document = KnowledgeDocument(
        id="page-3",
        container_id="DOC",
        title="Página atual",
        source_type="confluence_rest",
        metadata={
            "ancestors": [
                {
                    "id": "page-1",
                    "title": "Raiz",
                    "extensions": {"position": 1},
                    "_links": {"webui": "/pages/viewpage.action?pageId=1"},
                },
                {"id": 2, "title": "Seção", "_expandable": {"body": "body"}},
                {"id": "missing-title"},
                {"title": "missing-id"},
                {"id": {"value": "invalid"}, "title": "Inválido"},
                "invalid",
            ]
        },
    )

    metadata = knowledge_document_metadata(document, source)

    assert metadata["ancestors"] == [
        {"id": "page-1", "title": "Raiz"},
        {"id": "2", "title": "Seção"},
    ]
