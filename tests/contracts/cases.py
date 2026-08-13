from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from alquimista.connectors.base import KnowledgeSourceConnector
from alquimista.connectors.confluence import ConfluenceRestConnector
from alquimista.connectors.gitbook import GitBookConnector
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
)
