from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from alquimista.connectors import (
    ConfluenceRestConnector,
    GitBookConnector,
    ZendeskGuideConnector,
    default_registry,
)
from alquimista.connectors.http import ApiHttpClient
from alquimista.connectors.notion import NotionConnector
from alquimista.connectors.sharepoint import SharePointConnector
from alquimista.errors import (
    AuthenticationError,
    ConfluenceConnectionError,
    InvalidResponseError,
)
from alquimista.models import (
    AuthMode,
    ConnectorStatus,
    ExtractionOptions,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    KnowledgeSelection,
    ProjectConfig,
    SourceConfig,
)
from alquimista.runtime import CancellationToken
from alquimista.selection import SelectionStore
from alquimista.services import ConsolidationService, ExtractionService, SourceRuntime
from alquimista.ui.controllers import RuntimeBuilder, RuntimeSecrets


class FakeConfluenceClient:
    def __init__(self) -> None:
        self.closed = False

    def test_connection(self) -> dict[str, Any]:
        return {"spaces_visible": 2}

    def list_spaces(self) -> list[dict[str, str]]:
        return [
            {"key": "DOC", "name": "Documentação", "type": "global"},
            {"key": "OPS", "name": "Operação", "type": "global"},
        ]

    def list_pages(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "10",
                "title": "Página",
                "ancestors": [{"id": "1", "title": "Manual"}],
                "space": {"key": "DOC", "name": "Documentação"},
                "version": {"number": 2, "when": "2026-07-29T10:00:00Z"},
                "_links": {"webui": "/pages/viewpage.action?pageId=10"},
            }
        ]

    def fetch_page(self, page_id: str, *, include_body: bool, include_labels: bool = False) -> dict[str, Any]:
        return {
            "id": page_id,
            "title": "Página",
            "ancestors": [{"id": "1", "title": "Manual"}],
            "space": {"key": "DOC", "name": "Documentação"},
            "version": {"number": 2, "when": "2026-07-29T10:00:00Z"},
            "body": {"storage": {"value": "<p>Conteúdo normalizado</p>"}},
            "metadata": {"labels": {"results": []}},
            "_links": {"webui": "/pages/viewpage.action?pageId=10"},
        }

    @staticmethod
    def source_url(base_url: str, page: dict[str, Any]) -> str:
        return f"{base_url}/pages/viewpage.action?pageId={page['id']}"

    def close(self) -> None:
        self.closed = True


def test_registry_exposes_confluence_and_gitbook_as_implemented() -> None:
    registry = default_registry()
    assert registry.get("confluence_rest").implemented is True
    assert registry.get("sharepoint_graph").implemented is False
    assert registry.get("gitbook_api").implemented is True
    assert registry.get("zendesk_guide").implemented is True
    assert [item.source_type for item in registry.available()] == [
        "confluence_rest",
        "gitbook_api",
        "zendesk_guide",
    ]
    assert registry.get("notion_api").status_code is ConnectorStatus.DEVELOPMENT


class FailingConnectorClient:
    def __init__(self, error: Exception | None = None, payload: Any = None) -> None:
        self.error = error
        self.payload = payload

    def get_json(self, _path: str, **_kwargs: Any) -> Any:
        if self.error:
            raise self.error
        return self.payload

    def post_json(self, _path: str, **_kwargs: Any) -> Any:
        if self.error:
            raise self.error
        return self.payload

    def close(self) -> None:
        pass


class ProbeNotionConnector(NotionConnector):
    def get_document_children(self, _document_id: str) -> list[KnowledgeDocumentMetadata]:
        return []

    def normalize_document(self, _raw_document: object) -> KnowledgeDocument:
        raise NotImplementedError


class ProbeSharePointConnector(SharePointConnector):
    def get_document_children(self, _document_id: str) -> list[KnowledgeDocumentMetadata]:
        return []

    def normalize_document(self, _raw_document: object) -> KnowledgeDocument:
        raise NotImplementedError


def test_notion_does_not_hide_authentication_or_invalid_response_errors() -> None:
    connector = ProbeNotionConnector(
        SourceConfig(source_type="notion_api"),
        ExtractionOptions(),
        secret="token-not-real",
        client=FailingConnectorClient(AuthenticationError("token recusado")),  # type: ignore[arg-type]
    )
    with pytest.raises(AuthenticationError, match="token recusado"):
        connector.validate_connection()

    malformed = ProbeNotionConnector(
        SourceConfig(source_type="notion_api"),
        ExtractionOptions(),
        secret="token-not-real",
        client=FailingConnectorClient(payload=[]),  # type: ignore[arg-type]
    )
    with pytest.raises(InvalidResponseError, match="identidade inválida"):
        malformed.validate_connection()


def test_sharepoint_does_not_hide_api_errors_or_malformed_payloads() -> None:
    connector = ProbeSharePointConnector(
        SourceConfig(source_type="sharepoint_graph"),
        ExtractionOptions(),
        secret="token-not-real",
        client=FailingConnectorClient(AuthenticationError("permissão recusada")),  # type: ignore[arg-type]
    )
    with pytest.raises(AuthenticationError, match="permissão recusada"):
        connector.validate_connection()

    malformed = ProbeSharePointConnector(
        SourceConfig(source_type="sharepoint_graph"),
        ExtractionOptions(),
        secret="token-not-real",
        client=FailingConnectorClient(payload=[]),  # type: ignore[arg-type]
    )
    with pytest.raises(InvalidResponseError, match="site raiz inválido"):
        malformed.validate_connection()


def test_selection_store_keeps_same_document_id_in_different_containers() -> None:
    store = SelectionStore()
    store.set("source", "container-a", "doc-1", True)
    store.set("source", "container-b", "doc-1", True)
    store.set("other", "container-a", "doc-1", True)

    assert store.keys_for_source("source") == {
        "source:container-a:doc-1",
        "source:container-b:doc-1",
    }
    assert store.count_by_container("source")[("source", "container-a")] == 1
    assert len(store.selections()) == 3


def test_source_config_rejects_credentials_inside_connector_options() -> None:
    with pytest.raises(ValueError, match="Credenciais"):
        SourceConfig(connector_options={"access_token": "not-real"})

    source = SourceConfig(connector_options={"organization_id": "org-1"})
    assert source.connector_options["organization_id"] == "org-1"


def test_confluence_connector_maps_spaces_and_documents() -> None:
    source = SourceConfig(id="s1", base_url="https://example.test")
    client = FakeConfluenceClient()
    connector = ConfluenceRestConnector(
        source,
        ExtractionOptions(),
        client=client,  # type: ignore[arg-type]
    )
    containers = connector.list_containers()
    documents = connector.list_documents("DOC")
    document = connector.get_document("10")

    assert [item.id for item in containers] == ["DOC", "OPS"]
    assert documents[0].container_id == "DOC"
    assert document.content == "Conteúdo normalizado"
    assert document.source_type == "confluence_rest"
    connector.close()
    assert client.closed is True


class FakeGitBookClient:
    def __init__(self) -> None:
        self.closed = False
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        self.calls.append((path, params))
        if path == "/orgs/org-1":
            return {"id": "org-1", "title": "Organização sintética"}
        if path == "/orgs/org-1/spaces":
            if params and params.get("page") == "cursor-2":
                return {"items": [{"id": "space-2", "title": "Operação", "updatedAt": "2026-07-29T10:00:00Z"}]}
            return {
                "items": [
                    {
                        "id": "space-1",
                        "title": "Manual",
                        "visibility": "private",
                        "urls": {"app": "https://app.example/space-1"},
                    }
                ],
                "next": {"page": "cursor-2"},
            }
        if path == "/spaces/space-1/content/pages":
            return {
                "pages": [
                    {
                        "id": "page-root",
                        "title": "Introdução",
                        "createdAt": "2026-07-28T10:00:00Z",
                        "updatedAt": "2026-07-29T10:00:00Z",
                        "urls": {"app": "https://app.example/page-root"},
                        "pages": [
                            {
                                "id": "page-child",
                                "title": "Instalação",
                                "slug": "instalacao",
                                "updatedAt": "2026-07-29T11:00:00Z",
                                "urls": {"app": "https://app.example/page-child"},
                            }
                        ],
                    }
                ]
            }
        if path == "/spaces/space-2/content/pages":
            return {"pages": []}
        if path == "/spaces/space-1/content/page/page-child":
            return {
                "id": "page-child",
                "title": "Instalação",
                "markdown": "## Passos\n\n1. Baixe o aplicativo.",
                "updatedAt": "2026-07-29T11:00:00Z",
                "urls": {"app": "https://app.example/page-child"},
            }
        raise AssertionError(f"endpoint inesperado: {path}")

    def close(self) -> None:
        self.closed = True


def test_gitbook_connector_validates_paginates_rebuilds_hierarchy_and_normalizes() -> None:
    source = SourceConfig(
        id="gitbook-source",
        name="GitBook sintético",
        source_type="gitbook_api",
        space_key="org-1",
    )
    client = FakeGitBookClient()
    connector = GitBookConnector(
        source,
        ExtractionOptions(),
        secret="pat-not-real",
        client=client,  # type: ignore[arg-type]
    )

    assert connector.validate_connection()["organization_id"] == "org-1"
    containers = connector.list_containers()
    assert [item.id for item in containers] == ["space-1", "space-2"]
    documents = connector.list_documents("space-1")
    assert [item.id for item in documents] == ["page-root", "page-child"]
    assert documents[1].parent_id == "page-root"
    assert documents[1].metadata["ancestors"] == [{"id": "page-root", "title": "Introdução"}]
    assert documents[1].metadata["visibility"] == "private"
    assert documents[1].path == ["Introdução", "Instalação"]

    document = connector.get_document("page-child", container_id="space-1")
    assert document.content == "## Passos\n\n1. Baixe o aplicativo."
    assert document.original_url == "https://app.example/page-child"
    assert document.parent_id == "page-root"
    assert connector.get_document_children("page-root")[0].id == "page-child"

    connector.close()
    assert client.closed is True
    assert connector.secret == ""


def test_gitbook_runs_through_common_incremental_markdown_pipeline(tmp_path: Path) -> None:
    source = SourceConfig(
        id="gitbook-source",
        name="GitBook sintético",
        source_type="gitbook_api",
        space_key="org-1",
    )
    client = FakeGitBookClient()
    connector = GitBookConnector(
        source,
        ExtractionOptions(),
        secret="pat-not-real",
        client=client,  # type: ignore[arg-type]
    )
    connector.list_containers()
    metadata = connector.list_documents("space-1")
    project = ProjectConfig(output_dir="base", sources=[source])
    runtime = SourceRuntime(
        source=source,
        root={},
        pages_by_id={},
        selected_page_ids=["gitbook-source:space-1:page-child"],
        connector=connector,
        documents_by_container={"space-1": {item.id: item for item in metadata}},
    )

    first = ExtractionService(project, [runtime], tmp_path).run()
    second = ExtractionService(project, [runtime], tmp_path).run()

    assert first["counters"]["new"] == 1
    assert first["sources"][0]["containers"][0]["documents_selected"] == 1
    assert second["counters"]["unchanged"] == 1
    manifest = json.loads(
        (tmp_path / "base" / "manifesto_alquimista.json").read_text(encoding="utf-8")
    )
    entry = manifest["entries"][0]
    assert entry["source_type"] == "gitbook_api"
    assert entry["document_key"] == "gitbook-source:space-1:page-child"
    assert len(entry["content_hash"]) == 64
    output = (tmp_path / "base" / entry["markdown_path"]).read_text(encoding="utf-8")
    assert "Baixe o aplicativo" in output


class FakeHttpResponse:
    def __init__(self, status_code: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.content = b"binary-content"

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP status {self.status_code}")


class FakeHttpSession:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.trust_env = True
        self.responses = [
            FakeHttpResponse(429, {"error": {"code": 429}}, {"Retry-After": "0"}),
            FakeHttpResponse(200, {"items": []}, {"ETag": '"v1"'}),
        ]
        self.calls = 0

    def get(self, *_args: Any, **_kwargs: Any) -> FakeHttpResponse:
        response = self.responses[self.calls]
        self.calls += 1
        return response

    def post(self, *_args: Any, **_kwargs: Any) -> FakeHttpResponse:
        self.calls += 1
        return FakeHttpResponse(200, {"ok": True})

    def close(self) -> None:
        pass


def test_common_http_client_retries_rate_limit_without_logging_authorization() -> None:
    session = FakeHttpSession()
    logs: list[str] = []
    client = ApiHttpClient(
        "https://api.example/v1",
        ExtractionOptions(retry_count=2, max_requests_per_second=100),
        log=logs.append,
        headers={"Authorization": "Bearer secret-not-real"},
        session=session,  # type: ignore[arg-type]
    )

    assert client.get_json("/items") == {"items": []}
    assert session.calls == 2
    assert client.last_response_headers["etag"] == '"v1"'
    assert all("secret-not-real" not in message for message in logs)


def test_common_http_client_supports_post_json() -> None:
    session = FakeHttpSession()
    client = ApiHttpClient(
        "https://api.example/v1",
        ExtractionOptions(retry_count=2, max_requests_per_second=100),
        session=session,  # type: ignore[arg-type]
    )

    assert client.post_json("/query", json_body={"query": "value"}) == {"ok": True}


def test_common_http_client_supports_binary_download() -> None:
    session = FakeHttpSession()
    client = ApiHttpClient(
        "https://api.example/v1",
        ExtractionOptions(retry_count=2, max_requests_per_second=100),
        session=session,  # type: ignore[arg-type]
    )

    assert client.download("/file") == b"binary-content"


class FakeZendeskClient:
    def __init__(self) -> None:
        self.closed = False

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        if path in {"/help_center/categories.json", "/help_center/pt-br/categories.json"}:
            return {
                "categories": [{"id": 10, "name": "Manual", "html_url": "https://help.example/cat/10"}],
                "links": {"next": "https://zendesk.example/help_center/categories.json?page%5Bafter%5D=cursor-2"},
            }
        if path.startswith("https://zendesk.example/help_center/categories.json"):
            return {"categories": [{"id": 11, "name": "Operação"}], "links": {"next": None}}
        if path in {"/help_center/categories/10/sections.json", "/help_center/pt-br/categories/10/sections.json"}:
            return {"sections": [{"id": 20, "name": "Primeiros passos"}], "links": {"next": None}}
        if path in {"/help_center/sections/20/articles.json", "/help_center/pt-br/sections/20/articles.json"}:
            return {
                "articles": [
                    {
                        "id": 30,
                        "title": "Instalação",
                        "html_url": "https://help.example/articles/30",
                        "created_at": "2026-07-28T10:00:00Z",
                        "updated_at": "2026-07-29T10:00:00Z",
                        "locale": "pt-br",
                    }
                ],
                "links": {"next": None},
            }
        if path in {"/help_center/articles/30.json", "/help_center/pt-br/articles/30.json"}:
            return {
                "article": {
                    "id": 30,
                    "title": "Instalação",
                    "body": "<h2>Passos</h2><ol><li>Abra o aplicativo.</li></ol>",
                    "html_url": "https://help.example/articles/30",
                    "updated_at": "2026-07-29T10:00:00Z",
                    "locale": "pt-br",
                }
            }
        raise AssertionError(f"endpoint Zendesk inesperado: {path}")

    def close(self) -> None:
        self.closed = True


def test_zendesk_guide_connector_maps_category_sections_and_converts_html() -> None:
    source = SourceConfig(
        id="zendesk-source",
        name="Guide sintético",
        source_type="zendesk_guide",
        space_key="example",
        space_name="pt-br",
    )
    client = FakeZendeskClient()
    connector = ZendeskGuideConnector(
        source,
        ExtractionOptions(),
        secret="oauth-access-token-not-real",
        client=client,  # type: ignore[arg-type]
    )

    result = connector.validate_connection()
    assert result["subdomain"] == "example"
    containers = connector.list_containers()
    assert [item.id for item in containers] == ["10", "11"]
    documents = connector.list_documents("10")
    assert documents[0].parent_id == "20"
    assert documents[0].path == ["Manual", "Primeiros passos", "Instalação"]
    assert documents[0].metadata["ancestors"] == [{"id": "20", "title": "Primeiros passos"}]
    assert documents[0].metadata["visibility"] == "public"
    document = connector.get_document("30", container_id="10")
    assert "Abra o aplicativo" in document.content
    assert "## Passos" in document.content
    assert document.metadata["locale"] == "pt-br"
    connector.close()
    assert client.closed is True
    assert connector.secret == ""

def test_confluence_container_tree_uses_complete_descendant_inventory() -> None:
    """A árvore usa a busca de descendentes e não injeta páginas externas."""

    class FakeConfluenceClient:
        def __init__(self) -> None:
            self.closed = False

        def resolve_root(self) -> dict[str, Any]:
            return {"id": "root-1", "title": "Raiz", "space": {"key": "SPACE_A"}}

        def list_descendant_pages(self, root_id: str) -> list[dict[str, Any]]:
            assert root_id == "root-1"
            return [
                {"id": "folder-1", "title": "Pasta", "space": {"key": "SPACE_A"}},
                {
                    "id": "child-1",
                    "title": "Filho",
                    "ancestors": [{"id": "root-1", "title": "Raiz"}, {"id": "folder-1", "title": "Pasta"}],
                    "space": {"key": "SPACE_A"},
                },
                *[
                    {"id": f"page-{index}", "title": f"Página {index}", "space": {"key": "SPACE_A"}}
                    for index in range(1, 4001)
                ],
            ]

        def list_root_pages(self, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("o caminho hierárquico não deve substituir o CQL rápido")

        def list_child_pages(self, _parent_id: str, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("o caminho hierárquico não deve substituir o CQL rápido")

        def list_pages(self) -> list[dict[str, Any]]:
            raise AssertionError("a árvore não deve usar o inventário fora do escopo")

        def fetch_page(self, page_id: str, *, include_body: bool, include_labels: bool = False) -> dict[str, Any]:
            return {
                "id": page_id,
                "title": "Raiz" if page_id == "root-1" else page_id,
                "space": {"key": "SPACE_A"},
                "version": {"number": 1, "when": "2026-07-29T10:00:00Z"},
                "body": {"storage": {"value": "<p>Conteúdo</p>"}},
                "metadata": {"labels": {"results": []}},
                "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"},
            }

        @staticmethod
        def source_url(base_url: str, page: dict[str, Any]) -> str:
            return f"{base_url}/pages/viewpage.action?pageId={page['id']}"

        def close(self) -> None:
            self.closed = True

    source = SourceConfig(id="s1", base_url="https://example.test")
    connector = ConfluenceRestConnector(
        source,
        ExtractionOptions(),
        client=FakeConfluenceClient(),  # type: ignore[arg-type]
    )

    documents = connector.list_documents("SPACE_A")

    assert len(documents) == 4003
    assert [document.id for document in documents[:3]] == [
        "root-1",
        "folder-1",
        "child-1",
    ]
    assert documents[2].parent_id == "folder-1"
    connector.close()


def test_confluence_container_tree_falls_back_to_hierarchy_after_cql_500() -> None:
    class HierarchicalClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str | None]] = []

        def list_root_pages(
            self, *, cursor: str | None = None, limit: int = 100
        ) -> dict[str, Any]:
            del limit
            self.calls.append(("root", cursor))
            if cursor is None:
                return {
                    "results": [
                        {"id": "root-1", "title": "Raiz"}
                    ],
                    "next_cursor": "1",
                }
            return {
                "results": [{"id": "root-2", "title": "Outra raiz", "has_children": False}],
                "next_cursor": None,
            }

        def list_child_pages(
            self,
            parent_id: str,
            *,
            cursor: str | None = None,
            limit: int = 100,
        ) -> dict[str, Any]:
            del limit
            self.calls.append((parent_id, cursor))
            if parent_id == "root-1":
                return {
                    "results": [
                        {"id": "child-1", "title": "Filho"}
                    ],
                    "next_cursor": None,
                }
            if parent_id == "child-1":
                return {
                    "results": [{"id": "leaf-1", "title": "Folha", "has_children": False}],
                    "next_cursor": None,
                }
            return {"results": [], "next_cursor": None}

        def resolve_root(self) -> dict[str, Any]:
            return {"id": "cql-root", "title": "CQL"}

        def list_descendant_pages(self, root_id: str) -> list[dict[str, Any]]:
            assert root_id == "cql-root"
            raise ConfluenceConnectionError("HTTP 500 em /rest/api/content/search")

        def list_pages(self) -> list[dict[str, Any]]:
            raise ConfluenceConnectionError("HTTP 500 em /rest/api/content/search")

    client = HierarchicalClient()
    connector = ConfluenceRestConnector(
        SourceConfig(id="s1", base_url="https://example.test"),
        ExtractionOptions(),
        client=client,  # type: ignore[arg-type]
    )

    documents = connector.list_documents("SPACE_A")

    assert [document.id for document in documents] == [
        "root-1",
        "root-2",
        "child-1",
        "leaf-1",
    ]
    assert client.calls == [
        ("root", None),
        ("root", "1"),
        ("root-1", None),
        ("child-1", None),
    ]


def test_public_confluence_runtime_extracts_and_consolidates_without_cql(
    tmp_path: Path,
) -> None:
    class PublicClient:
        def __init__(self) -> None:
            self.cql_called = False
            self.hierarchy_called = False
            self.closed = False

        def list_spaces(self) -> list[dict[str, str]]:
            return [{"key": "SPACE_A", "name": "Público", "type": "global"}]

        def list_root_pages(
            self, *, cursor: str | None = None, limit: int = 100
        ) -> dict[str, Any]:
            self.hierarchy_called = True
            del cursor, limit
            return {
                "results": [
                    {
                        "id": "root-1",
                        "title": "Manual",
                        "space": {"key": "SPACE_A", "name": "Público"},
                    }
                ],
                "next_cursor": None,
            }

        def list_child_pages(
            self,
            parent_id: str,
            *,
            cursor: str | None = None,
            limit: int = 100,
        ) -> dict[str, Any]:
            self.hierarchy_called = True
            del cursor, limit
            if parent_id == "root-1":
                return {
                    "results": [
                        {
                            "id": "child-1",
                            "title": "Operação",
                            "ancestors": [{"id": "root-1", "title": "Manual"}],
                            "space": {"key": "SPACE_A", "name": "Público"},
                        }
                    ],
                    "next_cursor": None,
                }
            return {
                "results": [
                    {
                        "id": "leaf-1",
                        "title": "Configuração",
                        "ancestors": [
                            {"id": "root-1", "title": "Manual"},
                            {"id": "child-1", "title": "Operação"},
                        ],
                        "space": {"key": "SPACE_A", "name": "Público"},
                    }
                ],
                "next_cursor": None,
            }

        def resolve_root(self) -> dict[str, Any]:
            self.cql_called = True
            return {"id": "cql-root", "title": "CQL"}

        def list_descendant_pages(self, root_id: str) -> list[dict[str, Any]]:
            self.cql_called = True
            assert root_id == "cql-root"
            raise ConfluenceConnectionError("HTTP 500 em /rest/api/content/search")

        def list_pages(self) -> list[dict[str, Any]]:
            self.cql_called = True
            raise ConfluenceConnectionError("HTTP 500 em /rest/api/content/search")

        def fetch_page(
            self, page_id: str, *, include_body: bool, include_labels: bool = False
        ) -> dict[str, Any]:
            assert page_id == "leaf-1"
            assert include_body is True
            assert include_labels is True
            return {
                "id": page_id,
                "title": "Configuração",
                "ancestors": [
                    {"id": "root-1", "title": "Manual"},
                    {"id": "child-1", "title": "Operação"},
                ],
                "space": {"key": "SPACE_A", "name": "Público"},
                "version": {"number": 1, "when": "2026-08-09T10:00:00Z"},
                "body": {"storage": {"value": "<h1>Configuração</h1><p>Conteúdo.</p>"}},
                "metadata": {"labels": {"results": []}},
                "_links": {"webui": "/pages/viewpage.action?pageId=leaf-1"},
            }

        def close(self) -> None:
            self.closed = True

    source = SourceConfig(
        id="public-source",
        name="Confluence público",
        base_url="https://example.test",
        space_key="SPACE_A",
        auth_mode=AuthMode.PUBLIC,
    )
    project = ProjectConfig(
        output_dir="base",
        sources=[source],
        selections=[
            KnowledgeSelection(
                source_id=source.id,
                container_id="SPACE_A",
                document_id="leaf-1",
            )
        ],
    )
    client = PublicClient()
    connector = ConfluenceRestConnector(
        source,
        project.extraction,
        client=client,  # type: ignore[arg-type]
    )

    class Registry:
        def create(self, _source: SourceConfig, **_kwargs: Any) -> ConfluenceRestConnector:
            return connector

    runtimes = RuntimeBuilder({}, RuntimeSecrets(), Registry()).build_connectors(
        project,
        CancellationToken(),
        lambda _message: None,
    )
    runtime = runtimes[0]
    assert runtime.selected_page_ids == ["public-source:SPACE_A:leaf-1"]
    assert set(runtime.documents_by_container or {}) == {"SPACE_A"}

    document = connector.get_document("leaf-1", container_id="SPACE_A")
    assert document.content == "# Configuração\n\nConteúdo."

    extraction = ExtractionService(project, runtimes, tmp_path).run()
    manifest_path = tmp_path / "base" / "manifesto_alquimista.json"
    assert extraction["counters"]["new"] == 1
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    markdown_path = tmp_path / "base" / manifest["entries"][0]["markdown_path"]
    assert markdown_path.is_file()

    project.consolidation.grouping = "module"
    project.consolidation.module_depth = 5
    consolidation = ConsolidationService(project, tmp_path).run()
    assert consolidation["packages"] == 1
    assert consolidation["pages"] == 1
    assert client.cql_called is True
    assert client.hierarchy_called is True
    connector.close()
    assert client.closed is True



def test_zendesk_orders_items_by_position_without_reordering_ties() -> None:
    items = [
        {"id": "late", "position": 20},
        {"id": "first", "position": 1},
        {"id": "middle", "position": 10},
        {"id": "tie-a", "position": None},
        {"id": "tie-b", "position": None},
    ]

    ordered = ZendeskGuideConnector._ordered_items(items)

    assert [item["id"] for item in ordered] == ["first", "middle", "late", "tie-a", "tie-b"]


def test_zendesk_guide_runs_through_incremental_markdown_pipeline(tmp_path: Path) -> None:
    source = SourceConfig(
        id="zendesk-source",
        name="Guide sintético",
        source_type="zendesk_guide",
        space_key="example",
        space_name="pt-br",
    )
    connector = ZendeskGuideConnector(
        source,
        ExtractionOptions(),
        secret="oauth-access-token-not-real",
        client=FakeZendeskClient(),  # type: ignore[arg-type]
    )
    connector.list_containers()
    metadata = connector.list_documents("10")
    project = ProjectConfig(output_dir="base", sources=[source])
    runtime = SourceRuntime(
        source=source,
        root={},
        pages_by_id={},
        selected_page_ids=["zendesk-source:10:30"],
        connector=connector,
        documents_by_container={"10": {item.id: item for item in metadata}},
    )

    first = ExtractionService(project, [runtime], tmp_path).run()
    second = ExtractionService(project, [runtime], tmp_path).run()

    assert first["counters"]["new"] == 1
    assert second["counters"]["unchanged"] == 1
    manifest = json.loads(
        (tmp_path / "base" / "manifesto_alquimista.json").read_text(encoding="utf-8")
    )
    entry = manifest["entries"][0]
    assert entry["source_type"] == "zendesk_guide"
    assert entry["document_key"] == "zendesk-source:10:30"
    assert len(entry["content_hash"]) == 64


class FakeGenericConnector:
    def __init__(self) -> None:
        self.calls = 0

    def get_document(self, document_id: str) -> KnowledgeDocument:
        self.calls += 1
        return KnowledgeDocument(
            id=document_id,
            container_id="DOC",
            title="Página genérica",
            content="Conteúdo da base",
            original_url="https://example.test/document/10",
            updated_at=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
            source_type="fake_api",
            container_name="Documentação",
            path=["Manual", "Página genérica"],
        )

    def close(self) -> None:
        pass


def test_generic_runtime_writes_normalized_manifest_and_reuses_timestamp(
    tmp_path: Path,
) -> None:
    source = SourceConfig(id="s1", name="Fake API", source_type="fake_api")
    project = ProjectConfig(output_dir="base", sources=[source])
    metadata = KnowledgeDocumentMetadata(
        id="10",
        container_id="DOC",
        title="Página genérica",
        original_url="https://example.test/document/10",
        updated_at=datetime(2026, 7, 29, 10, tzinfo=timezone.utc),
        path=["Manual", "Página genérica"],
    )
    connector = FakeGenericConnector()
    runtime = SourceRuntime(
        source=source,
        root={},
        pages_by_id={},
        selected_page_ids=["s1:DOC:10"],
        connector=connector,
        documents_by_container={"DOC": {"10": metadata}},
    )

    first = ExtractionService(project, [runtime], tmp_path).run()
    second = ExtractionService(project, [runtime], tmp_path).run()

    assert first["counters"]["new"] == 1
    assert second["counters"]["unchanged"] == 1
    assert connector.calls == 1


def test_gitbook_flatten_pages_handles_deep_hierarchy_without_recursion() -> None:
    """Regression test: _flatten_pages must use an iterative stack so deeply
    nested GitBook pages do not raise RecursionError. Pythons default recursion
    limit is ~1000; a hierarchy of 3000 levels must flatten successfully and
    preserve _path/_ancestors ordering."""
    source = SourceConfig(
        id="gitbook-deep",
        name="GitBook deep nesting regression",
        source_type="gitbook_api",
        space_key="org-1",
    )

    depth = 3000
    # Build a single deeply nested chain iteratively to avoid exceeding the
    # recursion limit while constructing the fixture itself:
    # root -> l1 -> l2 -> ... -> l{depth-1}
    leaf = {"id": f"page-{depth - 1}", "title": f"L{depth - 1}"}
    for level in range(depth - 2, -1, -1):
        leaf = {"id": f"page-{level}", "title": f"L{level}", "pages": [leaf]}
    pages_root = [leaf]

    client = FakeGitBookClient()
    connector = GitBookConnector(
        source,
        ExtractionOptions(),
        secret="pat-not-real",
        client=client,  # type: ignore[arg-type]
    )

    # The recursive implementation would exceed the default recursion limit
    # (RecursionError); the iterative implementation must complete cleanly.
    flattened = connector._flatten_pages(pages_root, container_id="space-1")
    assert len(flattened) == depth
    # Pre-order DFS: first item is the root (level 0), last is deepest leaf.
    assert flattened[0]["_path"] == ["L0"]
    assert flattened[-1]["_path"] == [f"L{i}" for i in range(depth)]
    # ancestors accumulate along the chain; leaf has depth-1 ancestors.
    assert len(flattened[-1]["_ancestors"]) == depth - 1
    assert flattened[-1]["_ancestors"][0] == {"id": "page-0", "title": "L0"}
    assert flattened[-1]["_ancestors"][-1] == {"id": f"page-{depth - 2}", "title": f"L{depth - 2}"}
    # parent chain is preserved
    assert flattened[-1]["_parent_id"] == f"page-{depth - 2}"
    connector.close()


def test_gitbook_flatten_pages_preserves_pre_order_with_siblings() -> None:
    """Regression test: the iterative _flatten_pages must preserve true pre-order
    DFS (parent, full subtree, next sibling) even though it no longer recurses.
    A naive 'process all siblings then children' approach would yield a,b,b1,a1;
    pre-order must yield a,a1,b,b1."""
    source = SourceConfig(
        id="gitbook-order",
        name="GitBook sibling ordering regression",
        source_type="gitbook_api",
        space_key="org-1",
    )
    pages = [
        {
            "id": "a",
            "title": "A",
            "pages": [{"id": "a1", "title": "A1"}],
        },
        {
            "id": "b",
            "title": "B",
            "pages": [{"id": "b1", "title": "B1"}],
        },
    ]
    client = FakeGitBookClient()
    connector = GitBookConnector(
        source,
        ExtractionOptions(),
        secret="pat-not-real",
        client=client,  # type: ignore[arg-type]
    )
    flattened = connector._flatten_pages(pages, container_id="space-1")
    assert [item["id"] for item in flattened] == ["a", "a1", "b", "b1"]
    assert [item["_path"] for item in flattened] == [["A"], ["A", "A1"], ["B"], ["B", "B1"]]
    assert flattened[1]["_ancestors"] == [{"id": "a", "title": "A"}]
    assert flattened[3]["_ancestors"] == [{"id": "b", "title": "B"}]
    assert flattened[1]["_parent_id"] == "a"
    assert flattened[3]["_parent_id"] == "b"
    connector.close()
