from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from alquimista.connectors.base import KnowledgeSourceConnector
from alquimista.connectors.bookstack import BookStackConnector
from alquimista.connectors.confluence import ConfluenceRestConnector
from alquimista.connectors.generic_web import GenericWebConnector
from alquimista.connectors.gitbook import GitBookConnector
from alquimista.connectors.github_docs import GitHubDocsConnector
from alquimista.connectors.notion import NotionConnector
from alquimista.connectors.sharepoint import SharePointConnector
from alquimista.connectors.zendesk import ZendeskGuideConnector
from alquimista.models import ExtractionOptions, SourceConfig

_SECRET = "contract-secret-not-real"


def _confluence_page() -> dict[str, Any]:
    return {
        "id": "page-1",
        "type": "page",
        "title": "Contrato Confluence",
        "space": {"key": "DOC", "name": "Documentação"},
        "ancestors": [],
        "version": {"number": 1, "when": "2026-01-02T03:04:05Z"},
        "body": {"storage": {"value": "<h2>Contrato</h2><p>Conteúdo estável.</p>"}},
        "metadata": {"labels": {"results": [{"name": "contract"}]}},
    }


class _ConfluenceClient:
    def __init__(self) -> None:
        self.closed = False

    def test_connection(self) -> dict[str, Any]:
        return {"spaces_visible": 1, "identity": "contract"}

    def list_spaces(self) -> list[dict[str, Any]]:
        return [
            {"key": "DOC", "name": "Documentação", "type": "global"},
            {"key": "OPS", "name": "Operação", "type": "global"},
        ]

    def list_pages(self) -> list[dict[str, Any]]:
        return [_confluence_page()]

    def fetch_page(
        self,
        _document_id: str,
        *,
        include_body: bool = True,
        include_labels: bool = True,
    ) -> dict[str, Any]:
        del include_body, include_labels
        return _confluence_page()

    def list_root_pages(
        self, *, cursor: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        del cursor, limit
        return {"results": [_confluence_page()], "next_cursor": None}

    def list_child_pages(
        self,
        _parent_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        del cursor, limit
        return {"results": [], "next_cursor": None}

    def search_pages(
        self,
        _query: str,
        *,
        container_id: str,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        del container_id, cursor, limit
        return {"results": [_confluence_page()], "next_cursor": None, "etag": '"contract"'}

    def close(self) -> None:
        self.closed = True


class _GitBookClient:
    def __init__(self) -> None:
        self.closed = False
        self.last_response_headers = {"etag": '"contract"'}

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "/orgs/org-1":
            return {"id": "org-1", "title": "Organização"}
        if path == "/orgs/org-1/spaces":
            return {
                "items": [
                    {
                        "id": "space-1",
                        "title": "Documentação",
                        "visibility": "private",
                    },
                    {
                        "id": "space-2",
                        "title": "Operação",
                        "visibility": "private",
                    },
                ]
            }
        if path == "/spaces/space-1/content/pages":
            return {
                "pages": [
                    {
                        "id": "page-1",
                        "title": "Contrato GitBook",
                        "updatedAt": "2026-01-02T03:04:05Z",
                        "urls": {"app": "https://app.gitbook.test/page-1"},
                    }
                ]
            }
        if path == "/spaces/space-1/content/page/page-1":
            return {
                "id": "page-1",
                "title": "Contrato GitBook",
                "markdown": "## Contrato\n\nConteúdo estável.",
                "updatedAt": "2026-01-02T03:04:05Z",
                "urls": {"app": "https://app.gitbook.test/page-1"},
            }
        raise AssertionError(f"endpoint GitBook inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _ZendeskClient:
    def __init__(self) -> None:
        self.closed = False
        self.last_response_headers = {"etag": '"contract"'}

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "/help_center/pt-br/categories.json":
            return {
                "categories": [
                    {"id": 10, "name": "Documentação"},
                    {"id": 11, "name": "Operação"},
                ],
                "links": {"next": None},
            }
        if path == "/help_center/pt-br/categories/10/sections.json":
            return {
                "sections": [{"id": 20, "name": "Seção"}],
                "links": {"next": None},
            }
        if path == "/help_center/pt-br/sections/20/articles.json":
            return {
                "articles": [
                    {
                        "id": 30,
                        "title": "Contrato Zendesk",
                        "html_url": "https://help.test/articles/30",
                        "updated_at": "2026-01-02T03:04:05Z",
                        "locale": "pt-br",
                    }
                ],
                "links": {"next": None},
            }
        if path == "/help_center/pt-br/articles/30.json":
            return {
                "article": {
                    "id": 30,
                    "title": "Contrato Zendesk",
                    "body": "<h2>Contrato</h2><p>Conteúdo estável.</p>",
                    "html_url": "https://help.test/articles/30",
                    "updated_at": "2026-01-02T03:04:05Z",
                    "locale": "pt-br",
                }
            }
        raise AssertionError(f"endpoint Zendesk inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _NotionClient:
    def __init__(self) -> None:
        self.closed = False
        self.last_response_headers = {"etag": '"contract"'}

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "/users/me":
            return {"name": "Notion Integration"}
        if path == "/pages/page-1":
            return {
                "id": "page-1",
                "properties": {
                    "title": {
                        "type": "title",
                        "title": [{"plain_text": "Contrato Notion"}],
                    }
                },
                "url": "https://notion.test/page-1",
                "last_edited_time": "2026-01-02T03:04:05Z",
            }
        if path == "/blocks/page-1/children":
            return {
                "results": [
                    {
                        "id": "b1",
                        "type": "paragraph",
                        "paragraph": {"rich_text": [{"plain_text": "Conteúdo estável."}]},
                    }
                ],
                "has_more": False,
            }
        raise AssertionError(f"endpoint Notion GET inesperado: {path}")

    def post_json(self, path: str, *, json_body: dict[str, Any] | None = None) -> Any:
        del json_body
        if path == "/search":
            return {
                "results": [
                    {
                        "object": "database",
                        "id": "db-1",
                        "title": [{"plain_text": "Base Notion"}],
                    },
                    {
                        "object": "page",
                        "id": "page-1",
                        "properties": {
                            "title": {
                                "type": "title",
                                "title": [{"plain_text": "Contrato Notion"}],
                            }
                        },
                        "url": "https://notion.test/page-1",
                        "last_edited_time": "2026-01-02T03:04:05Z",
                    },
                ],
                "has_more": False,
            }
        if path == "/data_sources/db-1/query":
            return {
                "results": [
                    {
                        "object": "page",
                        "id": "page-1",
                        "properties": {
                            "title": {
                                "type": "title",
                                "title": [{"plain_text": "Contrato Notion"}],
                            }
                        },
                        "url": "https://notion.test/page-1",
                        "last_edited_time": "2026-01-02T03:04:05Z",
                    }
                ],
                "has_more": False,
            }
        raise AssertionError(f"endpoint Notion POST inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _GenericWebClient:
    def __init__(self) -> None:
        self.closed = False

    def get(self, url: str) -> tuple[str, str, dict[str, str], bytes]:
        html = (
            b"<html><head><title>Contrato Web</title></head>"
            b"<body><main><h1>Contrato Web</h1><p>Conte\xc3\xba\x64\x6f est\xc3\xa1vel.</p></main></body></html>"
        )
        return url, "text/html", {"ETag": '"contract"'}, html

    def close(self) -> None:
        self.closed = True


class _BookStackClient:
    def __init__(self) -> None:
        self.closed = False
        self.last_response_headers = {"etag": '"contract"'}

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "/books":
            return {
                "data": [
                    {
                        "id": 1,
                        "name": "Livro Contrato",
                        "slug": "livro-contrato",
                        "description": "Desc",
                        "created_at": "2026-01-02T03:04:05Z",
                        "updated_at": "2026-01-02T03:04:05Z",
                    }
                ],
                "total": 1,
            }
        if path == "/books/1":
            return {
                "id": 1,
                "name": "Livro Contrato",
                "contents": [
                    {
                        "type": "page",
                        "id": 10,
                        "name": "Contrato BookStack",
                        "slug": "contrato-bookstack",
                    }
                ],
            }
        if path == "/pages/10":
            return {
                "id": 10,
                "name": "Contrato BookStack",
                "slug": "contrato-bookstack",
                "book_id": 1,
                "markdown": "# Contrato BookStack\n\nConteúdo estável.",
                "created_at": "2026-01-02T03:04:05Z",
                "updated_at": "2026-01-02T03:04:05Z",
            }
        raise AssertionError(f"endpoint BookStack GET inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _GitHubDocsClient:
    def __init__(self) -> None:
        self.closed = False

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "/repos/org/repo":
            return {"full_name": "org/repo", "default_branch": "main"}
        if path == "/repos/org/repo/git/trees/main":
            return {
                "tree": [
                    {
                        "type": "blob",
                        "path": "docs/contrato.md",
                        "sha": "sha-contract-1",
                        "size": 100,
                    }
                ]
            }
        raise AssertionError(f"endpoint GitHub GET inesperado: {path}")

    def download(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        del params, headers
        if "docs/contrato.md" in path:
            return b"# Contrato GitHub Docs\n\nConteudo estavel."
        raise AssertionError(f"endpoint GitHub download inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _SharePointClient:
    def __init__(self) -> None:
        self.closed = False

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "/sites/root":
            return {"displayName": "SharePoint Root Site"}
        if path == "/sites?search=*":
            return {
                "value": [
                    {
                        "id": "site-1",
                        "displayName": "Site Contrato",
                        "name": "Site Contrato",
                    }
                ]
            }
        if path == "/sites/site-1/drive/root/children":
            return {
                "value": [
                    {
                        "id": "item-1",
                        "name": "Contrato SharePoint",
                        "webUrl": "https://sp.test/item-1",
                        "lastModifiedDateTime": "2026-01-02T03:04:05Z",
                    }
                ]
            }
        if path == "/drive/items/item-1":
            return {
                "id": "item-1",
                "name": "Contrato SharePoint",
                "webUrl": "https://sp.test/item-1",
                "lastModifiedDateTime": "2026-01-02T03:04:05Z",
            }
        if path == "/drive/items/item-1/children":
            return {"value": []}
        raise AssertionError(f"endpoint SharePoint GET inesperado: {path}")

    def download(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        del params, headers
        if "/drive/items/item-1/content" in path:
            return b"# Contrato SharePoint\n\nConteudo estavel."
        raise AssertionError(f"endpoint SharePoint download inesperado: {path}")

    def close(self) -> None:
        self.closed = True


@dataclass(frozen=True)
class BuiltConnector:
    connector: KnowledgeSourceConnector
    client: Any
    source: SourceConfig


@dataclass(frozen=True)
class ConnectorContractCase:
    source_type: str
    connector_type: type[KnowledgeSourceConnector]
    build: Callable[[], BuiltConnector]
    container_id: str
    document_id: str
    normalize_payload: Callable[[], dict[str, Any]]
    expected_container_ids: tuple[str, ...]
    expected_child_ids: tuple[str, ...] = ()
    optional_capabilities: frozenset[str] = frozenset()


def _build_confluence() -> BuiltConnector:
    client = _ConfluenceClient()
    source = SourceConfig(
        id="contract-confluence",
        name="Confluence Contract",
        source_type="confluence_rest",
        base_url="https://confluence.test",
        space_key="DOC",
    )
    connector = ConfluenceRestConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_gitbook() -> BuiltConnector:
    client = _GitBookClient()
    source = SourceConfig(
        id="contract-gitbook",
        name="GitBook Contract",
        source_type="gitbook_api",
        base_url="https://api.gitbook.com/v1",
        space_key="org-1",
    )
    connector = GitBookConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_zendesk() -> BuiltConnector:
    client = _ZendeskClient()
    source = SourceConfig(
        id="contract-zendesk",
        name="Zendesk Contract",
        source_type="zendesk_guide",
        base_url="https://example.zendesk.com/api/v2",
        space_key="example",
        space_name="pt-br",
    )
    connector = ZendeskGuideConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_notion() -> BuiltConnector:
    client = _NotionClient()
    source = SourceConfig(
        id="contract-notion",
        name="Notion Contract",
        source_type="notion_api",
        base_url="https://api.notion.com/v1",
        space_key="notion_workspace",
    )
    connector = NotionConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_bookstack() -> BuiltConnector:
    client = _BookStackClient()
    source = SourceConfig(
        id="contract-bookstack",
        name="BookStack Contract",
        source_type="bookstack_api",
        base_url="https://wiki.test/api",
        space_key="1",
    )
    connector = BookStackConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret="token_id:token_secret",
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_github_docs() -> BuiltConnector:
    client = _GitHubDocsClient()
    source = SourceConfig(
        id="contract-github",
        name="GitHub Docs Contract",
        source_type="github_docs",
        base_url="https://github.com/org/repo",
        space_key="org/repo",
        space_name="main",
        root_value="docs",
    )
    connector = GitHubDocsConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_generic_web() -> BuiltConnector:
    client = _GenericWebClient()
    source = SourceConfig(
        id="contract-generic-web",
        name="Generic Web Contract",
        source_type="generic_web",
        base_url="https://docs.test/page",
    )
    connector = GenericWebConnector(
        source,
        ExtractionOptions.model_validate({}),
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_sharepoint() -> BuiltConnector:
    client = _SharePointClient()
    source = SourceConfig(
        id="contract-sharepoint",
        name="SharePoint Contract",
        source_type="sharepoint_graph",
        base_url="https://graph.microsoft.com/v1.0",
        space_key="site-1",
    )
    connector = SharePointConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


CASES: tuple[ConnectorContractCase, ...] = (
    ConnectorContractCase(
        source_type="confluence_rest",
        connector_type=ConfluenceRestConnector,
        build=_build_confluence,
        container_id="DOC",
        document_id="page-1",
        normalize_payload=_confluence_page,
        expected_container_ids=("DOC",),
        optional_capabilities=frozenset(
            {"list_root_documents", "list_document_children", "search_documents"}
        ),
    ),
    ConnectorContractCase(
        source_type="gitbook_api",
        connector_type=GitBookConnector,
        build=_build_gitbook,
        container_id="space-1",
        document_id="page-1",
        normalize_payload=lambda: {
            "id": "page-1",
            "title": "Contrato GitBook",
            "markdown": "## Contrato\n\nConteúdo estável.",
            "updatedAt": "2026-01-02T03:04:05Z",
            "urls": {"app": "https://app.gitbook.test/page-1"},
            "_container_id": "space-1",
        },
        expected_container_ids=("space-1", "space-2"),
    ),
    ConnectorContractCase(
        source_type="zendesk_guide",
        connector_type=ZendeskGuideConnector,
        build=_build_zendesk,
        container_id="10",
        document_id="30",
        normalize_payload=lambda: {
            "id": 30,
            "title": "Contrato Zendesk",
            "body": "<h2>Contrato</h2><p>Conteúdo estável.</p>",
            "html_url": "https://help.test/articles/30",
            "updated_at": "2026-01-02T03:04:05Z",
            "locale": "pt-br",
            "_container_id": "10",
            "_section_id": "20",
            "_section_name": "Seção",
            "_category_name": "Documentação",
        },
        expected_container_ids=("10", "11"),
    ),
    ConnectorContractCase(
        source_type="notion_api",
        connector_type=NotionConnector,
        build=_build_notion,
        container_id="notion_workspace",
        document_id="page-1",
        normalize_payload=lambda: {
            "id": "page-1",
            "title": "Contrato Notion",
            "markdown": "Conteúdo estável.",
            "last_edited_time": "2026-01-02T03:04:05Z",
            "url": "https://notion.test/page-1",
            "_container_id": "notion_workspace",
        },
        expected_container_ids=("notion_workspace", "db-1"),
        expected_child_ids=("b1",),
        optional_capabilities=frozenset(
            {"list_root_documents", "list_document_children", "search_documents"}
        ),
    ),
    ConnectorContractCase(
        source_type="bookstack_api",
        connector_type=BookStackConnector,
        build=_build_bookstack,
        container_id="1",
        document_id="10",
        normalize_payload=lambda: {
            "id": 10,
            "name": "Contrato BookStack",
            "markdown": "# Contrato BookStack\n\nConteúdo estável.",
            "created_at": "2026-01-02T03:04:05Z",
            "updated_at": "2026-01-02T03:04:05Z",
            "_container_id": "1",
        },
        expected_container_ids=("1",),
    ),
    ConnectorContractCase(
        source_type="github_docs",
        connector_type=GitHubDocsConnector,
        build=_build_github_docs,
        container_id="org_repo",
        document_id="sha-contract-1",
        normalize_payload=lambda: {
            "id": "sha-contract-1",
            "title": "Contrato",
            "markdown": "# Contrato GitHub Docs\n\nConteudo estavel.",
            "path": ["docs", "contrato.md"],
            "_container_id": "org_repo",
        },
        expected_container_ids=("org_repo",),
    ),
    ConnectorContractCase(
        source_type="generic_web",
        connector_type=GenericWebConnector,
        build=_build_generic_web,
        container_id="docs.test",
        document_id="4197d23b3f693fbdcf9edde6f9874ab112de293176f9ac95b4b27f4f8f1db8d3",
        normalize_payload=lambda: {
            "id": "4197d23b3f693fbdcf9edde6f9874ab112de293176f9ac95b4b27f4f8f1db8d3",
            "title": "Contrato Web",
            "markdown": "# Contrato Web\n\nConteúdo estável.",
            "url": "https://docs.test/page",
            "container_id": "docs.test",
        },
        expected_container_ids=("docs.test",),
    ),
    ConnectorContractCase(
        source_type="sharepoint_graph",
        connector_type=SharePointConnector,
        build=_build_sharepoint,
        container_id="site-1",
        document_id="item-1",
        normalize_payload=lambda: {
            "id": "item-1",
            "title": "Contrato SharePoint",
            "markdown": "# Contrato SharePoint\n\nConteudo estavel.",
            "webUrl": "https://sp.test/item-1",
            "_container_id": "site-1",
        },
        expected_container_ids=("site-1",),
    ),
)

