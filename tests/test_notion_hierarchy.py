"""Notion pages and subpages: hierarchy, lazy tree and per-page content."""
from __future__ import annotations

from typing import Any

from alquimista.connectors.notion import NotionConnector
from alquimista.connectors.notion_parser import NotionDocumentParser
from alquimista.models import ExtractionOptions, SourceConfig


def _rich(text: str) -> list[dict[str, Any]]:
    return [{"plain_text": text}]


def _page(page_id: str, title: str, parent: dict[str, Any]) -> dict[str, Any]:
    return {
        "object": "page",
        "id": page_id,
        "parent": parent,
        "url": f"https://www.notion.so/{page_id}",
        "last_edited_time": "2026-09-01T10:00:00.000Z",
        "properties": {"Name": {"type": "title", "title": _rich(title)}},
    }


def _block(block_id: str, btype: str, *, has_children: bool = False, **data: Any) -> dict[str, Any]:
    return {"object": "block", "id": block_id, "type": btype, "has_children": has_children, btype: data}


PAGES = [
    _page("A", "Manual", {"type": "workspace", "workspace": True}),
    _page("B", "Instalação", {"type": "page_id", "page_id": "A"}),
    _page("C", "Windows", {"type": "page_id", "page_id": "B"}),
    _page("D", "Avulsa", {"type": "page_id", "page_id": "nao-compartilhada"}),
]
BLOCKS = {
    "A": [
        _block("h", "heading_1", rich_text=_rich("Manual")),
        _block("p", "paragraph", rich_text=_rich("Bem-vindo")),
        _block("B", "child_page", has_children=True, title="Instalação"),
        _block("t", "toggle", has_children=True, rich_text=_rich("Mais")),
    ],
    "t": [_block("tp", "paragraph", rich_text=_rich("Detalhe oculto"))],
    "B": [
        _block("bp", "paragraph", rich_text=_rich("Conteúdo de instalação")),
        _block("C", "child_page", title="Windows"),
    ],
    "C": [_block("cp", "paragraph", rich_text=_rich("Passos no Windows"))],
}


class FakeNotion:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def post_json(self, path: str, *, json_body: Any = None, params: Any = None) -> dict[str, Any]:
        self.requests.append(path)
        assert path == "/search"
        database = {"object": "database", "id": "db", "title": _rich("Tarefas")}
        return {"results": [*PAGES, database], "has_more": False}

    def get_json(self, path: str, *, params: Any = None) -> dict[str, Any]:
        self.requests.append(path)
        if path.startswith("/pages/"):
            return next(page for page in PAGES if page["id"] == path.split("/")[-1])
        block_id = path.split("/")[2]
        return {"results": BLOCKS[block_id], "has_more": False}

    def close(self) -> None:
        pass


def _connector() -> tuple[NotionConnector, FakeNotion]:
    client = FakeNotion()
    source = SourceConfig(id="n", name="Wiki", source_type="notion_api", base_url="https://api.notion.com/v1")
    return NotionConnector(source, ExtractionOptions(), secret="secret", client=client), client  # type: ignore[arg-type]


def test_full_listing_keeps_hierarchy_and_paths() -> None:
    connector, _ = _connector()

    documents = {doc.id: doc for doc in connector.list_documents("notion_workspace")}

    assert set(documents) == {"A", "B", "C", "D"}  # the database is not a page
    assert documents["C"].parent_id == "B"
    assert documents["C"].path == ["Manual", "Instalação", "Windows"]
    assert documents["D"].path == ["Avulsa"]


def test_lazy_tree_shows_roots_and_only_subpages_as_children() -> None:
    connector, _ = _connector()

    roots = connector.list_root_documents("notion_workspace")
    children = connector.list_document_children("notion_workspace", "A")

    # D's parent is not shared with the integration, so D is a root too.
    assert {item.title for item in roots.items} == {"Manual", "Avulsa"}
    assert [(item.id, item.title) for item in children.items] == [("B", "Instalação")]


def test_page_content_links_subpages_instead_of_inlining_them() -> None:
    connector, client = _connector()

    document = connector.get_document("A")

    assert "Bem-vindo" in document.content and "Detalhe oculto" in document.content
    assert "[Instalação](https://www.notion.so/B)" in document.content
    assert "Conteúdo de instalação" not in document.content
    assert "/blocks/B/children" not in client.requests
    assert document.parent_id is None


def test_parser_renders_common_blocks() -> None:
    blocks = [
        _block("1", "heading_2", rich_text=_rich("Seção")),
        _block("2", "bulleted_list_item", rich_text=_rich("item")),
        _block("3", "numbered_list_item", rich_text=_rich("passo")),
        _block("4", "to_do", rich_text=_rich("feito"), checked=True),
        _block("5", "code", rich_text=_rich("print(1)"), language="python"),
        _block("6", "quote", rich_text=_rich("citação")),
        _block("7", "divider"),
    ]
    blocks[1]["_children"] = [_block("2a", "bulleted_list_item", rich_text=_rich("subitem"))]

    assert NotionDocumentParser().render(blocks) == (
        "## Seção\n\n- item\n\n  - subitem\n\n1. passo\n\n- [x] feito\n\n```python\nprint(1)\n```\n\n> citação\n\n---"
    )
