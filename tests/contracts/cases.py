from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alquimista.connectors.base import KnowledgeSourceConnector
from alquimista.connectors.bookstack import BookStackConnector
from alquimista.connectors.confluence import ConfluenceRestConnector
from alquimista.connectors.contentful import ContentfulConnector
from alquimista.connectors.document360 import Document360Connector
from alquimista.connectors.freshdesk import FreshdeskConnector
from alquimista.connectors.generic_docs import GenericDocsConnector
from alquimista.connectors.generic_web import GenericWebConnector
from alquimista.connectors.ghost import GhostConnector
from alquimista.connectors.gitbook import GitBookConnector
from alquimista.connectors.github_docs import GitHubDocsConnector
from alquimista.connectors.gitlab import GitLabDocsConnector
from alquimista.connectors.guru import GuruConnector
from alquimista.connectors.helpjuice import HelpjuiceConnector
from alquimista.connectors.helpscout import HelpScoutConnector
from alquimista.connectors.hubspot import HubSpotConnector
from alquimista.connectors.intercom import IntercomConnector
from alquimista.connectors.local_files import LocalFilesConnector
from alquimista.connectors.mediawiki import MediaWikiConnector
from alquimista.connectors.notion import NotionConnector
from alquimista.connectors.outline import OutlineConnector
from alquimista.connectors.readme import ReadMeConnector
from alquimista.connectors.salesforce import SalesforceConnector
from alquimista.connectors.sanity import SanityConnector
from alquimista.connectors.sharepoint import SharePointConnector
from alquimista.connectors.slite import SliteConnector
from alquimista.connectors.strapi import StrapiConnector
from alquimista.connectors.wordpress import WordPressConnector
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


class _MockResponse:
    def __init__(self, data: Any) -> None:
        self._data = data

    def json(self) -> Any:
        return self._data


class _FreshdeskClient:
    def __init__(self) -> None:
        self.closed = False

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> _MockResponse:
        del params
        if "/api/v2/solutions/categories?per_page=1" in path:
            return _MockResponse([{"id": 1, "name": "Geral"}])
        if "/api/v2/solutions/categories?per_page=100" in path:
            return _MockResponse([{"id": 1, "name": "Geral", "description": "Categoria Geral"}])
        if "/api/v2/solutions/categories/1/folders" in path:
            return _MockResponse([{"id": 10, "name": "Pasta 1", "category_id": 1}])
        if "/api/v2/solutions/folders/10/articles" in path:
            return _MockResponse([
                {
                    "id": 100,
                    "title": "Contrato Freshdesk",
                    "folder_id": 10,
                    "status": 2,
                    "updated_at": "2026-01-02T03:04:05Z",
                    "created_at": "2026-01-02T03:04:05Z",
                }
            ])
        if "/api/v2/solutions/articles/100" in path:
            return _MockResponse({
                "id": 100,
                "title": "Contrato Freshdesk",
                "description": "<h2>Contrato Freshdesk</h2><p>Conteúdo estável.</p>",
                "folder_id": 10,
                "status": 2,
                "updated_at": "2026-01-02T03:04:05Z",
            })
        raise AssertionError(f"endpoint Freshdesk GET inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _OutlineClient:
    def __init__(self) -> None:
        self.closed = False

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> _MockResponse:
        del json
        if path == "/collections.list":
            return _MockResponse({
                "data": [
                    {
                        "id": "col-1",
                        "name": "Coleção Outline",
                        "description": "Coleção de teste",
                        "urlId": "colecao-outline",
                    }
                ]
            })
        if path == "/documents.list":
            return _MockResponse({
                "data": [
                    {
                        "id": "doc-1",
                        "title": "Contrato Outline",
                        "text": "## Contrato Outline\n\nConteúdo estável.",
                        "collectionId": "col-1",
                        "updatedAt": "2026-01-02T03:04:05Z",
                        "url": "/doc/doc-1",
                    }
                ]
            })
        if path == "/documents.info":
            return _MockResponse({
                "data": {
                    "id": "doc-1",
                    "title": "Contrato Outline",
                    "text": "## Contrato Outline\n\nConteúdo estável.",
                    "collectionId": "col-1",
                    "updatedAt": "2026-01-02T03:04:05Z",
                    "url": "/doc/doc-1",
                }
            })
        raise AssertionError(f"endpoint Outline POST inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _HelpScoutClient:
    def __init__(self) -> None:
        self.closed = False

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> _MockResponse:
        del params
        if "/collections?page=1&pageSize=1" in path:
            return _MockResponse({"collections": {"items": [{"id": "col-1", "name": "Docs"}]}})
        if "/collections?page=1&pageSize=50" in path:
            return _MockResponse({
                "collections": {
                    "items": [{"id": "col-1", "name": "Docs", "slug": "docs", "visibility": "public"}],
                    "pages": 1,
                }
            })
        if "/collections/col-1/articles" in path or "/articles?page=1" in path:
            return _MockResponse({
                "articles": {
                    "items": [
                        {
                            "id": "art-1",
                            "name": "Contrato Help Scout",
                            "collectionId": "col-1",
                            "status": "published",
                            "updatedAt": "2026-01-02T03:04:05Z",
                        }
                    ],
                    "pages": 1,
                }
            })
        if "/articles/art-1" in path:
            return _MockResponse({
                "article": {
                    "id": "art-1",
                    "name": "Contrato Help Scout",
                    "text": "<h2>Contrato Help Scout</h2><p>Conteúdo estável.</p>",
                    "collectionId": "col-1",
                    "status": "published",
                    "updatedAt": "2026-01-02T03:04:05Z",
                }
            })
        raise AssertionError(f"endpoint Help Scout GET inesperado: {path}")

    def close(self) -> None:
        self.closed = True


class _Document360Client:
    def __init__(self) -> None:
        self.closed = False

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> _MockResponse:
        del params
        if "/Categories" in path:
            return _MockResponse({
                "data": [{"id": "cat-1", "name": "Categoria D360", "slug": "cat-1"}]
            })
        if "/Articles?category_id=cat-1" in path or path == "/Articles":
            return _MockResponse({
                "data": [
                    {
                        "id": "art-1",
                        "title": "Contrato Document360",
                        "category_id": "cat-1",
                        "updated_at": "2026-01-02T03:04:05Z",
                    }
                ]
            })
        if "/Articles/art-1" in path:
            return _MockResponse({
                "data": {
                    "id": "art-1",
                    "title": "Contrato Document360",
                    "content": "## Contrato Document360\n\nConteúdo estável.",
                    "category_id": "cat-1",
                    "updated_at": "2026-01-02T03:04:05Z",
                }
            })
        raise AssertionError(f"endpoint Document360 GET inesperado: {path}")

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


def _build_freshdesk() -> BuiltConnector:
    client = _FreshdeskClient()
    source = SourceConfig(
        id="contract-freshdesk",
        name="Freshdesk Contract",
        source_type="freshdesk_solutions",
        base_url="https://domain.freshdesk.com",
    )
    connector = FreshdeskConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_outline() -> BuiltConnector:
    client = _OutlineClient()
    source = SourceConfig(
        id="contract-outline",
        name="Outline Contract",
        source_type="outline_api",
        base_url="https://app.getoutline.com/api",
    )
    connector = OutlineConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_helpscout() -> BuiltConnector:
    client = _HelpScoutClient()
    source = SourceConfig(
        id="contract-helpscout",
        name="Help Scout Contract",
        source_type="helpscout_docs",
        base_url="https://docsapi.helpscout.net/v1",
    )
    connector = HelpScoutConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


def _build_document360() -> BuiltConnector:
    client = _Document360Client()
    source = SourceConfig(
        id="contract-document360",
        name="Document360 Contract",
        source_type="document360_api",
        base_url="https://apihub.document360.io/v2",
    )
    connector = Document360Connector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _GenericDocsMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get(self, url: str) -> tuple[str, str, dict[str, str], bytes]:
        return (url, "text/html", {}, b"<h1>Contrato Docs</h1><p>Conteudo estavel.</p>")
    def close(self) -> None:
        self.closed = True


def _build_generic_docs() -> BuiltConnector:
    client = _GenericDocsMockClient()
    source = SourceConfig(
        id="contract-generic-docs",
        name="Web Docs Contract",
        source_type="generic_docs",
        base_url="https://docs.test",
    )
    connector = GenericDocsConnector(
        source,
        ExtractionOptions.model_validate({}),
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _IntercomMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "me":
            return {"name": "Admin", "type": "admin"}
        if path == "help_center/collections":
            return {"data": [{"id": "col-1", "name": "Geral"}]}
        if path == "articles":
            return {"data": [{"id": "art-1", "title": "Contrato Intercom", "parent_id": "col-1", "url": "https://help.test/art-1"}]}
        if path == "articles/art-1":
            return {"id": "art-1", "title": "Contrato Intercom", "body": "<h2>Contrato Intercom</h2><p>Conteúdo estável.</p>", "url": "https://help.test/art-1"}
        if path == "conversations":
            return {"conversations": []}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_intercom() -> BuiltConnector:
    client = _IntercomMockClient()
    source = SourceConfig(
        id="contract-intercom",
        name="Intercom Contract",
        source_type="intercom_api",
        base_url="https://api.intercom.io",
    )
    connector = IntercomConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _SalesforceMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if "sobjects/Knowledge__kav/art-1" in path:
            return {"Id": "art-1", "Title": "Contrato Salesforce", "ArticleBody": "Conteúdo estável."}
        if "sobjects" in path:
            return {"sobjects": []}
        if "query" in path:
            return {"records": [{"Id": "art-1", "Title": "Contrato Salesforce", "Summary": "Conteúdo estável."}]}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_salesforce() -> BuiltConnector:
    client = _SalesforceMockClient()
    source = SourceConfig(
        id="contract-salesforce",
        name="Salesforce Contract",
        source_type="salesforce_api",
        base_url="https://login.salesforce.com",
    )
    connector = SalesforceConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _HubSpotMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if "tickets" in path:
            return {"results": []}
        if path == "cms/v3/blogs/posts":
            return {"results": [{"id": "post-1", "name": "Contrato HubSpot", "url": "https://hub.test/post-1"}]}
        if path == "cms/v3/blogs/posts/post-1":
            return {"id": "post-1", "name": "Contrato HubSpot", "postBody": "<p>Conteúdo estável.</p>", "url": "https://hub.test/post-1"}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_hubspot() -> BuiltConnector:
    client = _HubSpotMockClient()
    source = SourceConfig(
        id="contract-hubspot",
        name="HubSpot Contract",
        source_type="hubspot_api",
        base_url="https://api.hubapi.com",
    )
    connector = HubSpotConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _HelpjuiceMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "categories":
            return [{"id": "cat-1", "name": "Geral"}]
        if path == "categories/cat-1/questions":
            return [{"id": "q-1", "name": "Contrato Helpjuice", "url": "https://hj.test/q-1"}]
        if path == "questions/q-1":
            return {"id": "q-1", "name": "Contrato Helpjuice", "answer": "<p>Conteúdo estável.</p>", "url": "https://hj.test/q-1"}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_helpjuice() -> BuiltConnector:
    client = _HelpjuiceMockClient()
    source = SourceConfig(
        id="contract-helpjuice",
        name="Helpjuice Contract",
        source_type="helpjuice_api",
        base_url="https://help.helpjuice.com",
    )
    connector = HelpjuiceConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _GuruMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "collections":
            return [{"id": "col-1", "name": "Geral"}]
        if path == "search/cards":
            return [{"id": "card-1", "preferredPhrase": "Contrato Guru"}]
        if path == "cards/card-1":
            return {"id": "card-1", "preferredPhrase": "Contrato Guru", "content": "<p>Conteúdo estável.</p>"}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_guru() -> BuiltConnector:
    client = _GuruMockClient()
    source = SourceConfig(
        id="contract-guru",
        name="Guru Contract",
        source_type="guru_api",
        base_url="https://api.getguru.com/api/v1",
    )
    connector = GuruConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _SliteMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "channels":
            return [{"id": "ch-1", "name": "Geral"}]
        if path == "channels/ch-1/notes":
            return [{"id": "note-1", "title": "Contrato Slite"}]
        if path == "notes/note-1":
            return {"id": "note-1", "title": "Contrato Slite", "markdown": "## Contrato Slite\n\nConteúdo estável."}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_slite() -> BuiltConnector:
    client = _SliteMockClient()
    source = SourceConfig(
        id="contract-slite",
        name="Slite Contract",
        source_type="slite_api",
        base_url="https://api.slite.com/v1",
    )
    connector = SliteConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _MediaWikiMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del path
        p = params or {}
        action = p.get("action")
        if action == "query" and p.get("meta") == "siteinfo":
            return {"query": {"general": {"sitename": "Wiki"}}}
        if action == "query" and p.get("list") == "allcategories":
            return {"query": {"allcategories": []}}
        if action == "query" and p.get("list") == "allpages":
            return {"query": {"allpages": [{"pageid": "1", "title": "Contrato MediaWiki"}]}}
        if action == "parse":
            return {"parse": {"pageid": "1", "displaytitle": "Contrato MediaWiki", "text": {"*": "<p>Conteúdo estável.</p>"}}}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_mediawiki() -> BuiltConnector:
    client = _MediaWikiMockClient()
    source = SourceConfig(
        id="contract-mediawiki",
        name="MediaWiki Contract",
        source_type="mediawiki_api",
        base_url="https://pt.wikipedia.org/w/api.php",
    )
    connector = MediaWikiConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _ReadMeMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "version":
            return [{"version": "v1"}]
        if path == "categories":
            return [{"slug": "cat-1", "title": "Geral"}]
        if path == "categories/cat-1/docs":
            return [{"slug": "doc-1", "title": "Contrato ReadMe"}]
        if path == "docs/doc-1":
            return {"slug": "doc-1", "title": "Contrato ReadMe", "body": "## Contrato ReadMe\n\nConteúdo estável."}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_readme() -> BuiltConnector:
    client = _ReadMeMockClient()
    source = SourceConfig(
        id="contract-readme",
        name="ReadMe Contract",
        source_type="readme_api",
        base_url="https://dash.readme.com/api/v1",
    )
    connector = ReadMeConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _GitLabMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if "api/v4/projects/org%2Frepo/wikis/home" in path:
            return {"slug": "home", "title": "Contrato GitLab", "content": "## Contrato GitLab\n\nConteúdo estável."}
        if "api/v4/projects/org%2Frepo/wikis" in path:
            return [{"slug": "home", "title": "Contrato GitLab"}]
        if "api/v4/projects/org%2Frepo" in path:
            return {"name": "Repo", "web_url": "https://gitlab.com/org/repo"}
        return []
    def close(self) -> None:
        self.closed = True


def _build_gitlab() -> BuiltConnector:
    client = _GitLabMockClient()
    source = SourceConfig(
        id="contract-gitlab",
        name="GitLab Contract",
        source_type="gitlab_docs",
        base_url="https://gitlab.com/org/repo",
        space_key="org/repo",
    )
    connector = GitLabDocsConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _WordPressMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path.endswith("wp-json/wp/v2/posts/1"):
            return {"id": "1", "title": {"rendered": "Contrato WordPress"}, "content": {"rendered": "<p>Conteúdo estável.</p>"}, "link": "https://wp.test/1"}
        if path.endswith("wp-json/wp/v2/posts"):
            return [{"id": "1", "title": {"rendered": "Contrato WordPress"}, "link": "https://wp.test/1"}]
        if path.endswith("wp-json/wp/v2"):
            return {"name": "WordPress"}
        return []
    def close(self) -> None:
        self.closed = True


def _build_wordpress() -> BuiltConnector:
    client = _WordPressMockClient()
    source = SourceConfig(
        id="contract-wordpress",
        name="WordPress Contract",
        source_type="wordpress_api",
        base_url="https://wp.test/wp-json/wp/v2",
    )
    connector = WordPressConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _GhostMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if "settings" in path:
            return {"settings": {"title": "Ghost"}}
        if "posts/post-1" in path:
            return {"posts": [{"id": "post-1", "title": "Contrato Ghost", "html": "<p>Conteúdo estável.</p>", "url": "https://ghost.test/post-1"}]}
        if path.endswith("posts/"):
            return {"posts": [{"id": "post-1", "title": "Contrato Ghost", "url": "https://ghost.test/post-1"}]}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_ghost() -> BuiltConnector:
    client = _GhostMockClient()
    source = SourceConfig(
        id="contract-ghost",
        name="Ghost Contract",
        source_type="ghost_api",
        base_url="https://ghost.test",
    )
    connector = GhostConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _StrapiMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if path == "api/articles":
            return {"data": [{"id": "1", "attributes": {"title": "Contrato Strapi"}}], "meta": {}}
        if path == "api/articles/1":
            return {"data": {"id": "1", "attributes": {"title": "Contrato Strapi", "content": "<p>Conteúdo estável.</p>"}}}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_strapi() -> BuiltConnector:
    client = _StrapiMockClient()
    source = SourceConfig(
        id="contract-strapi",
        name="Strapi Contract",
        source_type="strapi_api",
        base_url="https://strapi.test/api",
        space_key="articles",
    )
    connector = StrapiConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _ContentfulMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del params
        if "content_types" in path:
            return {"items": [{"sys": {"id": "article"}, "name": "Article"}]}
        if path.endswith("entry-1"):
            return {"sys": {"id": "entry-1"}, "fields": {"title": "Contrato Contentful", "body": "<p>Conteúdo estável.</p>"}}
        if "entries" in path:
            return {"items": [{"sys": {"id": "entry-1"}, "fields": {"title": "Contrato Contentful"}}]}
        if "spaces" in path:
            return {"name": "Space 1"}
        return {}
    def close(self) -> None:
        self.closed = True


def _build_contentful() -> BuiltConnector:
    client = _ContentfulMockClient()
    source = SourceConfig(
        id="contract-contentful",
        name="Contentful Contract",
        source_type="contentful_api",
        base_url="https://cdn.contentful.com",
        space_key="space-1",
    )
    connector = ContentfulConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _SanityMockClient:
    def __init__(self) -> None:
        self.closed = False
    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        del path
        p = params or {}
        q = p.get("query", "")
        if "unique" in q:
            return {"result": ["article"]}
        if '_id == "doc-1"' in q:
            return {"result": {"_id": "doc-1", "_type": "article", "title": "Contrato Sanity", "content": "<p>Conteúdo estável.</p>"}}
        if "article" in q:
            return {"result": [{"_id": "doc-1", "_type": "article", "title": "Contrato Sanity"}]}
        return {"result": []}
    def close(self) -> None:
        self.closed = True


def _build_sanity() -> BuiltConnector:
    client = _SanityMockClient()
    source = SourceConfig(
        id="contract-sanity",
        name="Sanity Contract",
        source_type="sanity_api",
        base_url="https://sanity_project.api.sanity.io",
        space_key="sanity_project",
        space_name="production",
    )
    connector = SanityConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret=_SECRET,
        client=client,  # type: ignore[arg-type]
    )
    return BuiltConnector(connector, client, source)


class _LocalFilesHarnessClient:
    def __init__(self) -> None:
        self.closed = False
    def close(self) -> None:
        self.closed = True


def _build_local_files() -> BuiltConnector:
    import tempfile
    client = _LocalFilesHarnessClient()
    temp_dir = Path(tempfile.gettempdir()) / "alquimista_contract_local"
    temp_dir.mkdir(parents=True, exist_ok=True)
    sample_file = temp_dir / "contrato.md"
    sample_file.write_text("# Contrato Local\n\nConteúdo estável.", encoding="utf-8")

    source = SourceConfig(
        id="contract-local-files",
        name="Local Files Contract",
        source_type="local_files",
        base_url=str(temp_dir),
        connector_options={"path": str(temp_dir)},
    )
    connector = LocalFilesConnector(
        source,
        ExtractionOptions.model_validate({}),
        secret="",
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
    ConnectorContractCase(
        source_type="freshdesk_solutions",
        connector_type=FreshdeskConnector,
        build=_build_freshdesk,
        container_id="1",
        document_id="100",
        normalize_payload=lambda: {
            "id": 100,
            "title": "Contrato Freshdesk",
            "description": "<h2>Contrato Freshdesk</h2><p>Conteúdo estável.</p>",
            "updated_at": "2026-01-02T03:04:05Z",
            "_container_id": "1",
        },
        expected_container_ids=("1",),
    ),
    ConnectorContractCase(
        source_type="outline_api",
        connector_type=OutlineConnector,
        build=_build_outline,
        container_id="col-1",
        document_id="doc-1",
        normalize_payload=lambda: {
            "id": "doc-1",
            "title": "Contrato Outline",
            "text": "## Contrato Outline\n\nConteúdo estável.",
            "updatedAt": "2026-01-02T03:04:05Z",
            "_container_id": "col-1",
        },
        expected_container_ids=("col-1",),
    ),
    ConnectorContractCase(
        source_type="helpscout_docs",
        connector_type=HelpScoutConnector,
        build=_build_helpscout,
        container_id="col-1",
        document_id="art-1",
        normalize_payload=lambda: {
            "id": "art-1",
            "name": "Contrato Help Scout",
            "text": "<h2>Contrato Help Scout</h2><p>Conteúdo estável.</p>",
            "updatedAt": "2026-01-02T03:04:05Z",
            "_container_id": "col-1",
        },
        expected_container_ids=("col-1",),
    ),
    ConnectorContractCase(
        source_type="document360_api",
        connector_type=Document360Connector,
        build=_build_document360,
        container_id="cat-1",
        document_id="art-1",
        normalize_payload=lambda: {
            "id": "art-1",
            "title": "Contrato Document360",
            "content": "## Contrato Document360\n\nConteúdo estável.",
            "updated_at": "2026-01-02T03:04:05Z",
            "_container_id": "cat-1",
        },
        expected_container_ids=("cat-1",),
    ),
    ConnectorContractCase(
        source_type="generic_docs",
        connector_type=GenericDocsConnector,
        build=_build_generic_docs,
        container_id="docs.test",
        document_id="c0a373d5ffcb4e03d42045e0d4a7a8d839bbdbcf54b1f4fa9fc5bc15b0b2e887",
        normalize_payload=lambda: {
            "id": "c0a373d5ffcb4e03d42045e0d4a7a8d839bbdbcf54b1f4fa9fc5bc15b0b2e887",
            "title": "Contrato Docs",
            "content": "# Contrato Docs\n\nConteudo estavel.",
            "original_url": "https://docs.test",
            "source_type": "generic_docs",
            "container_id": "docs.test",
        },
        expected_container_ids=("docs.test",),

    ),
    ConnectorContractCase(
        source_type="intercom_api",
        connector_type=IntercomConnector,
        build=_build_intercom,
        container_id="collection_col-1",
        document_id="art-1",
        normalize_payload=lambda: {
            "id": "art-1",
            "title": "Contrato Intercom",
            "content": "## Contrato Intercom\n\nConteúdo estável.",
            "original_url": "https://help.test/art-1",
            "source_type": "intercom_api",
            "container_id": "collection_col-1",
        },
        expected_container_ids=("collection_col-1", "support_conversations"),
    ),
    ConnectorContractCase(
        source_type="salesforce_api",
        connector_type=SalesforceConnector,
        build=_build_salesforce,
        container_id="salesforce_knowledge",
        document_id="art-1",
        normalize_payload=lambda: {
            "id": "art-1",
            "title": "Contrato Salesforce",
            "content": "Conteúdo estável.",
            "source_type": "salesforce_api",
            "container_id": "salesforce_knowledge",
        },
        expected_container_ids=("salesforce_knowledge", "salesforce_cases"),
    ),
    ConnectorContractCase(
        source_type="hubspot_api",
        connector_type=HubSpotConnector,
        build=_build_hubspot,
        container_id="hubspot_knowledge",
        document_id="post-1",
        normalize_payload=lambda: {
            "id": "post-1",
            "title": "Contrato HubSpot",
            "content": "Conteúdo estável.",
            "original_url": "https://hub.test/post-1",
            "source_type": "hubspot_api",
            "container_id": "hubspot_knowledge",
        },
        expected_container_ids=("hubspot_knowledge", "hubspot_tickets"),
    ),
    ConnectorContractCase(
        source_type="helpjuice_api",
        connector_type=HelpjuiceConnector,
        build=_build_helpjuice,
        container_id="cat-1",
        document_id="q-1",
        normalize_payload=lambda: {
            "id": "q-1",
            "title": "Contrato Helpjuice",
            "content": "Conteúdo estável.",
            "original_url": "https://hj.test/q-1",
            "source_type": "helpjuice_api",
            "container_id": "cat-1",
        },
        expected_container_ids=("cat-1",),
    ),
    ConnectorContractCase(
        source_type="guru_api",
        connector_type=GuruConnector,
        build=_build_guru,
        container_id="col-1",
        document_id="card-1",
        normalize_payload=lambda: {
            "id": "card-1",
            "title": "Contrato Guru",
            "content": "Conteúdo estável.",
            "source_type": "guru_api",
            "container_id": "col-1",
        },
        expected_container_ids=("col-1",),
    ),
    ConnectorContractCase(
        source_type="slite_api",
        connector_type=SliteConnector,
        build=_build_slite,
        container_id="ch-1",
        document_id="note-1",
        normalize_payload=lambda: {
            "id": "note-1",
            "title": "Contrato Slite",
            "content": "## Contrato Slite\n\nConteúdo estável.",
            "source_type": "slite_api",
            "container_id": "ch-1",
        },
        expected_container_ids=("ch-1",),
    ),
    ConnectorContractCase(
        source_type="mediawiki_api",
        connector_type=MediaWikiConnector,
        build=_build_mediawiki,
        container_id="main",
        document_id="1",
        normalize_payload=lambda: {
            "id": "1",
            "title": "Contrato MediaWiki",
            "content": "Conteúdo estável.",
            "source_type": "mediawiki_api",
            "container_id": "main",
        },
        expected_container_ids=("main",),
    ),
    ConnectorContractCase(
        source_type="readme_api",
        connector_type=ReadMeConnector,
        build=_build_readme,
        container_id="cat-1",
        document_id="doc-1",
        normalize_payload=lambda: {
            "id": "doc-1",
            "title": "Contrato ReadMe",
            "content": "## Contrato ReadMe\n\nConteúdo estável.",
            "source_type": "readme_api",
            "container_id": "cat-1",
        },
        expected_container_ids=("cat-1",),
    ),
    ConnectorContractCase(
        source_type="gitlab_docs",
        connector_type=GitLabDocsConnector,
        build=_build_gitlab,
        container_id="wiki",
        document_id="home",
        normalize_payload=lambda: {
            "id": "home",
            "title": "Contrato GitLab",
            "content": "## Contrato GitLab\n\nConteúdo estável.",
            "source_type": "gitlab_docs",
            "container_id": "wiki",
        },
        expected_container_ids=("wiki", "repository"),
    ),
    ConnectorContractCase(
        source_type="wordpress_api",
        connector_type=WordPressConnector,
        build=_build_wordpress,
        container_id="posts",
        document_id="1",
        normalize_payload=lambda: {
            "id": "1",
            "title": "Contrato WordPress",
            "content": "Conteúdo estável.",
            "original_url": "https://wp.test/1",
            "source_type": "wordpress_api",
            "container_id": "posts",
        },
        expected_container_ids=("posts", "pages"),
    ),
    ConnectorContractCase(
        source_type="ghost_api",
        connector_type=GhostConnector,
        build=_build_ghost,
        container_id="posts",
        document_id="post-1",
        normalize_payload=lambda: {
            "id": "post-1",
            "title": "Contrato Ghost",
            "content": "Conteúdo estável.",
            "original_url": "https://ghost.test/post-1",
            "source_type": "ghost_api",
            "container_id": "posts",
        },
        expected_container_ids=("posts", "pages"),
    ),
    ConnectorContractCase(
        source_type="strapi_api",
        connector_type=StrapiConnector,
        build=_build_strapi,
        container_id="articles",
        document_id="1",
        normalize_payload=lambda: {
            "id": "1",
            "title": "Contrato Strapi",
            "content": "Conteúdo estável.",
            "source_type": "strapi_api",
            "container_id": "articles",
        },
        expected_container_ids=("articles",),
    ),
    ConnectorContractCase(
        source_type="contentful_api",
        connector_type=ContentfulConnector,
        build=_build_contentful,
        container_id="article",
        document_id="entry-1",
        normalize_payload=lambda: {
            "id": "entry-1",
            "title": "Contrato Contentful",
            "content": "# Contrato Contentful\n\n## Body\n\nConteúdo estável.",
            "source_type": "contentful_api",
            "container_id": "article",
        },
        expected_container_ids=("article",),
    ),
    ConnectorContractCase(
        source_type="sanity_api",
        connector_type=SanityConnector,
        build=_build_sanity,
        container_id="article",
        document_id="doc-1",
        normalize_payload=lambda: {
            "id": "doc-1",
            "title": "Contrato Sanity",
            "content": "# Contrato Sanity\n\n## Content\n\nConteúdo estável.",
            "source_type": "sanity_api",
            "container_id": "article",
        },
        expected_container_ids=("article",),
    ),
)



