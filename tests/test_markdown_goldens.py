from __future__ import annotations

import json

import pytest
from golden_helpers import ROOT, assert_golden_json, assert_golden_text

from alquimista.connectors.confluence_parser import ConfluenceDocumentParser
from alquimista.markdown import (
    KnowledgeDocumentRenderer,
    MarkdownTransformer,
    sha256_text,
)
from alquimista.models import MarkdownOptions, SourceConfig


def _page(name: str = "page_full.json") -> dict[str, object]:
    return json.loads(
        (ROOT / "confluence" / name).read_text(encoding="utf-8")
    )


def _source() -> SourceConfig:
    return SourceConfig(
        id="golden-source",
        name="Confluence golden",
        base_url="https://example.test",
        space_key="DOCS",
        space_name="Documentação",
    )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "page_full.json",
        "page_empty.json",
        "page_partial.json",
        "page_nested_macros.json",
    ],
)
def test_confluence_parser_matches_approved_transformer_body(
    fixture_name: str,
) -> None:
    page = _page(fixture_name)
    source = _source()
    options = MarkdownOptions()
    root = {
        "id": "root-1",
        "title": "Manual",
        "space": page.get("space", {}),
    }
    legacy = MarkdownTransformer(
        type("Client", (), {"base_url": source.base_url})(), source, root, options
    ).technical_markdown(page)
    parsed = ConfluenceDocumentParser(source, options).parse(page)
    assert parsed.content == legacy
    if fixture_name == "page_full.json":
        assert parsed.metadata["labels"] == ["p0", "confluence"]
        assert {item["filename"] for item in parsed.attachments} == {
            "guia.pdf",
            "diagrama.png",
        }


def test_confluence_default_body_is_frozen_as_golden() -> None:
    page = _page()
    source = _source()
    parsed = ConfluenceDocumentParser(source, MarkdownOptions()).parse(page)
    golden_path = ROOT / "confluence" / "approved_parser_default.md"
    assert_golden_text(parsed.content, golden_path)


def test_confluence_content_flags_have_deterministic_golden() -> None:
    page = _page()
    source = _source()
    options = MarkdownOptions(
        include_images=False,
        include_attachments=False,
        include_videos=False,
        include_links=False,
        include_tables=False,
        include_code_blocks=False,
        include_panels=False,
        include_expand_macros=False,
        include_content_macros=False,
    )
    parsed = ConfluenceDocumentParser(source, options).parse(page)
    assert_golden_text(
        parsed.content,
        ROOT / "confluence" / "approved_parser_content_disabled.md",
    )


def test_empty_page_has_empty_body_and_approved_rendering() -> None:
    source = _source()
    document = ConfluenceDocumentParser(source, MarkdownOptions()).parse(
        _page("page_empty.json")
    )
    renderer = KnowledgeDocumentRenderer(MarkdownOptions())
    prepared = renderer.prepare(document, source)
    output = renderer.render_prepared(
        prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    assert document.content == ""
    assert_golden_text(
        output,
        ROOT / "confluence" / "approved_document_empty.md",
        exact=True,
    )


def test_partial_payload_has_safe_defaults_and_does_not_leak_secrets() -> None:
    secret = "GOLDEN_SECRET_MUST_NOT_LEAK"
    page = _page("page_partial.json")
    source = _source()
    source.username = secret
    document = ConfluenceDocumentParser(source, MarkdownOptions()).parse(page)
    renderer = KnowledgeDocumentRenderer(MarkdownOptions())
    prepared = renderer.prepare(document, source)
    output = renderer.render_prepared(
        prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    serialized_document = json.dumps(
        document.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
    )
    assert secret in json.dumps(page)
    assert secret not in serialized_document
    assert secret not in output
    assert_golden_json(
        document.model_dump(mode="json"),
        ROOT / "confluence" / "approved_partial_document.json",
    )
    assert_golden_text(
        output,
        ROOT / "confluence" / "approved_document_partial.md",
        exact=True,
    )


def test_unknown_and_nested_macros_have_approved_output() -> None:
    document = ConfluenceDocumentParser(_source(), MarkdownOptions()).parse(
        _page("page_nested_macros.json")
    )
    assert_golden_text(
        document.content,
        ROOT / "confluence" / "approved_parser_nested_macros.md",
    )


def test_minimum_preset_has_approved_document() -> None:
    source = _source()
    options = MarkdownOptions.preset("minimum")
    document = ConfluenceDocumentParser(source, options).parse(_page())
    renderer = KnowledgeDocumentRenderer(options)
    prepared = renderer.prepare(document, source)
    output = renderer.render_prepared(
        prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    assert_golden_text(
        output,
        ROOT / "confluence" / "approved_document_minimum.md",
        exact=True,
    )


@pytest.mark.parametrize(
    ("preset", "golden_name"),
    [
        ("traceability", "approved_document_traceability.md"),
        ("rag", "approved_document_rag.md"),
    ],
)
def test_detailed_and_rag_presets_have_approved_documents(
    preset: str, golden_name: str
) -> None:
    source = _source()
    options = MarkdownOptions.preset(preset)
    document = ConfluenceDocumentParser(source, options).parse(_page())
    renderer = KnowledgeDocumentRenderer(options)
    prepared = renderer.prepare(document, source)
    output = renderer.render_prepared(
        prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    assert_golden_text(
        output,
        ROOT / "confluence" / golden_name,
        exact=True,
    )


@pytest.mark.parametrize(
    "field",
    [
        "include_images",
        "include_attachments",
        "include_videos",
        "include_links",
        "include_tables",
        "include_code_blocks",
        "include_panels",
        "include_expand_macros",
        "include_content_macros",
        "remove_html_comments",
        "remove_noise",
        "absolute_links",
    ],
)
def test_each_parser_flag_matches_approved_transformer(field: str) -> None:
    page = _page()
    source = _source()
    options = MarkdownOptions(**{field: False})
    legacy = MarkdownTransformer(
        type("Client", (), {"base_url": source.base_url})(),
        source,
        {"id": "root-1", "title": "Manual", "space": page["space"]},
        options,
    ).technical_markdown(page)
    parsed = ConfluenceDocumentParser(source, options).parse(page)
    assert parsed.content == legacy
    expected = json.loads(
        (ROOT / "confluence" / "approved_parser_flags.json").read_text(
            encoding="utf-8"
        )
    )
    assert parsed.content == expected[field]


@pytest.mark.parametrize("metadata_style", ["markdown", "yaml", "both", "none"])
def test_each_metadata_style_has_static_snapshot(metadata_style: str) -> None:
    source = _source()
    options = MarkdownOptions(metadata_style=metadata_style)
    document = ConfluenceDocumentParser(source, options).parse(_page())
    renderer = KnowledgeDocumentRenderer(options)
    output = renderer.render_prepared(
        renderer.prepare(document, source),
        "2026-08-12T12:00:00-03:00",
        "new",
    )
    expected = json.loads(
        (ROOT / "confluence" / "approved_metadata_styles.json").read_text(
            encoding="utf-8"
        )
    )
    assert output == expected[metadata_style]


def test_renderer_hash_and_output_are_deterministic() -> None:
    page = _page()
    source = _source()
    document = ConfluenceDocumentParser(source, MarkdownOptions()).parse(page)
    renderer = KnowledgeDocumentRenderer(MarkdownOptions())
    prepared = renderer.prepare(document, source)
    output = renderer.render_prepared(
        prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    assert prepared.content_hash == sha256_text(
        renderer.hash_input(prepared.metadata, prepared.content)
    )
    assert_golden_text(
        output,
        ROOT / "confluence" / "approved_document_default.md",
        exact=True,
    )
    assert sha256_text(output) == sha256_text(output.replace("\r\n", "\n"))
    assert output.endswith("\n")


@pytest.mark.parametrize(
    "fixture_name",
    [
        "page_full.json",
        "page_empty.json",
        "page_partial.json",
        "page_nested_macros.json",
    ],
)
def test_parse_prepare_and_render_are_repeatable(fixture_name: str) -> None:
    source = _source()
    options = MarkdownOptions()
    parser = ConfluenceDocumentParser(source, options)
    renderer = KnowledgeDocumentRenderer(options)
    first_document = parser.parse(_page(fixture_name))
    second_document = parser.parse(_page(fixture_name))
    first_prepared = renderer.prepare(first_document, source)
    second_prepared = renderer.prepare(second_document, source)
    first_output = renderer.render_prepared(
        first_prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    second_output = renderer.render_prepared(
        second_prepared, "2026-08-12T12:00:00-03:00", "new"
    )
    assert first_document == second_document
    assert first_prepared == second_prepared
    assert first_output == second_output
