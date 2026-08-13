from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from ..browser.contracts import (
    CancellationLike,
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
    Visibility,
)
from ..client import ConfluenceClient
from ..errors import ConfluenceConnectionError
from ..models import (
    ConnectorCapabilities,
    ExtractionOptions,
    KnowledgeContainer,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    KnowledgeSource,
    MarkdownOptions,
    SourceConfig,
)
from ..runtime import CancellationToken, LogCallback
from .base import KnowledgeSourceConnector
from .confluence_parser import ConfluenceDocumentParser

_UNSET = object()
_LAZY_BATCH_LIMIT = 100
_LAZY_MAX_ITEMS = 5000


def _datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class ConfluenceRestConnector(KnowledgeSourceConnector):
    """Confluence adapter. API details stay inside this module and its client."""

    SOURCE_TYPE = "confluence_rest"

    def __init__(
        self,
        source: SourceConfig,
        options: ExtractionOptions,
        *,
        secret: str = "",
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        client: ConfluenceClient | None = None,
        markdown_options: MarkdownOptions | None = None,
    ) -> None:
        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self._injected_client = client is not None
        self.client = client or ConfluenceClient(
            source,
            options,
            secret=secret,
            token=self.token,
            log=self.log,
        )
        self._containers: dict[str, KnowledgeContainer] = {}
        self._documents: dict[str, dict[str, Any]] = {}

    def configure_markdown(self, options: MarkdownOptions) -> None:
        self.markdown_options = options

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name,
            base_url=self.source.base_url,
            connector_version="1",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_attachments=True,
            supports_permissions=True,
            supports_search=True,
            supports_updated_at=True,
            supports_public_access=True,
            supports_bearer_token=True,
            supports_lazy_discovery=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        return self.client.test_connection()

    def list_containers(self) -> list[KnowledgeContainer]:
        self.log(
            f"[Confluence] Descobrindo espaços da fonte {self.source.id} "
            f"({self.source.base_url or '<base_url vazia>'})"
        )
        containers = []
        for item in self.client.list_spaces():
            identifier = str(item.get("key") or item.get("id") or "")
            if not identifier:
                continue
            container = KnowledgeContainer(
                id=identifier,
                key=str(item.get("key") or identifier),
                name=str(item.get("name") or identifier),
                container_type="space",
                source_type=self.SOURCE_TYPE,
                metadata={
                    "remote_type": item.get("type", ""),
                    "icon": item.get("icon"),
                    "icon_url": urljoin(
                        self.source.base_url.rstrip("/") + "/",
                        str(
                            (item.get("icon") or {}).get("path")
                            or (item.get("icon") or {}).get("url")
                            or ""
                        ),
                    )
                    if (item.get("icon") or {}).get("path")
                    or (item.get("icon") or {}).get("url")
                    else "",
                },
            )
            self._containers[identifier] = container
            containers.append(container)

        if self.source.space_key:
            configured = next(
                (
                    container
                    for container in containers
                    if container.id == self.source.space_key
                ),
                None,
            )
            if configured is not None:
                self.log("[Confluence] 1 espaço configurado disponível.")
                return [configured]
            specified = KnowledgeContainer(
                id=self.source.space_key,
                key=self.source.space_key,
                name=self.source.space_name or self.source.space_key,
                container_type="space",
                source_type=self.SOURCE_TYPE,
            )
            self._containers[self.source.space_key] = specified
            containers.insert(0, specified)

        self.log(f"[Confluence] {len(containers)} espaços disponíveis.")
        return containers

    def _client_for_container(self, container_id: str) -> ConfluenceClient:
        configured = self.source.model_copy(
            update={
                "space_key": container_id,
                "space_name": self._containers.get(
                    container_id,
                    KnowledgeContainer(
                        id=container_id,
                        name=container_id,
                        container_type="space",
                        source_type=self.SOURCE_TYPE,
                    ),
                ).name,
                "root_mode": "space",
                "root_value": "",
            }
        )
        return ConfluenceClient(
            configured,
            self.options,
            secret=self.secret,
            token=self.token,
            log=self.log,
        )

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        self.log(f"[Confluence] Descobrindo páginas do espaço {container_id}.")
        if self._injected_client:
            raw_pages = self._ordered_pages(self.client, container_id)
        else:
            with self._client_for_container(container_id) as client:
                raw_pages = self._ordered_pages(client, container_id)
        result = [self._metadata(page, container_id) for page in raw_pages]
        self._documents.update(
            {item.id: raw for item, raw in zip(result, raw_pages, strict=True)}
        )
        self.log(f"[Confluence] {len(result)} páginas descobertas no espaço {container_id}.")
        return result

    @staticmethod
    def _ordered_pages(client: Any, container_id: str) -> list[dict[str, Any]]:
        """Return the selected container tree in provider response order.

        Keep the historical CQL inventory as the fast path. Some Confluence
        instances return HTTP 5xx for descendant CQL searches; those clients
        transparently fall back to the hierarchical endpoints used by lazy
        discovery.
        """
        resolve_root = getattr(client, "resolve_root", None)
        list_descendants = getattr(client, "list_descendant_pages", None)
        if callable(resolve_root) and callable(list_descendants):
            root = resolve_root()
            root_id = str(root.get("id") or "")
            if root_id:
                try:
                    return [root, *list_descendants(root_id)]
                except ConfluenceConnectionError as exc:
                    if not any(f"HTTP {status}" in str(exc) for status in (500, 502, 503, 504)):
                        raise

        # Some public Confluence installations reject only the descendant
        # CQL (``ancestor=...``) while accepting the space inventory CQL.
        # Retain that older, fast-compatible route before requiring a
        # homepage-based hierarchical traversal.
        try:
            return client.list_pages()
        except ConfluenceConnectionError as exc:
            if not any(f"HTTP {status}" in str(exc) for status in (500, 502, 503, 504)):
                raise

        list_roots = getattr(client, "list_root_pages", None)
        list_children = getattr(client, "list_child_pages", None)
        if callable(list_roots) and callable(list_children):
            return ConfluenceRestConnector._ordered_hierarchical_pages(
                list_roots,
                list_children,
            )
        raise ConfluenceConnectionError(
            "O Confluence recusou tanto a busca de descendentes quanto o inventário "
            "do espaço; não foi possível carregar as páginas por hierarquia."
        )

    @staticmethod
    def _ordered_hierarchical_pages(
        list_roots: Any,
        list_children: Any,
    ) -> list[dict[str, Any]]:
        """Traverse hierarchy after a transient failure of the CQL path."""
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()

        def child_state(page: dict[str, Any]) -> bool | None:
            """Return child state; None means the provider omitted it."""
            for key in ("has_children", "hasChildren"):
                value = page.get(key)
                if isinstance(value, bool):
                    return value
            children = page.get("children")
            if isinstance(children, dict) and isinstance(children.get("size"), int):
                return children["size"] > 0
            links = page.get("_links") or {}
            if isinstance(links, dict) and isinstance(links.get("child"), str):
                return True
            return None

        def collect_children(parent_ids: list[str]) -> None:
            pending = list(reversed(parent_ids))
            while pending:
                parent_id = pending.pop()
                child_ids: list[str] = []
                cursor: str | None = None
                while True:
                    payload = list_children(parent_id, cursor=cursor, limit=100)
                    results = payload.get("results", [])
                    if not isinstance(results, list):
                        break
                    for page in results:
                        page_id = str(page.get("id", ""))
                        if not page_id or page_id in seen:
                            continue
                        seen.add(page_id)
                        ordered.append(page)
                        if child_state(page) is not False:
                            child_ids.append(page_id)
                    cursor = payload.get("next_cursor")
                    if not cursor or not results:
                        break
                pending.extend(reversed(child_ids))

        cursor: str | None = None
        root_children: list[str] = []
        while True:
            payload = list_roots(cursor=cursor, limit=100)
            results = payload.get("results", [])
            if not isinstance(results, list):
                break
            for page in results:
                page_id = str(page.get("id", ""))
                if not page_id or page_id in seen:
                    continue
                seen.add(page_id)
                ordered.append(page)
                if child_state(page) is not False:
                    root_children.append(page_id)
            cursor = payload.get("next_cursor")
            if not cursor or not results:
                break
        if root_children:
            collect_children(root_children)
        return ordered

    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        raw = self.client.fetch_page(
            str(document_id),
            include_body=True,
            include_labels=True,
        )
        container_id = str((raw.get("space") or {}).get("key") or self.source.space_key)
        return self.normalize_document(raw | {"container_id": container_id})

    def get_document_children(
        self, document_id: str
    ) -> list[KnowledgeDocumentMetadata]:
        raw = self._documents.get(str(document_id))
        container_id = str(
            ((raw or {}).get("space") or {}).get("key") or self.source.space_key
        )
        return [
            item
            for item in self.list_documents(container_id)
            if item.parent_id == str(document_id)
        ]

    def _lazy_request(
        self,
        container_id: str,
        operation: Any,
    ) -> dict[str, Any]:
        if self._injected_client:
            return operation(self.client)
        with self._client_for_container(container_id) as client:
            return operation(client)

    def _collect_lazy_pages(
        self,
        container_id: str,
        fetch: Callable[[ConfluenceClient, str | None, int], dict[str, Any]],
        *,
        cursor: str | None,
        limit: int,
        token: CancellationLike | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Consume one complete lazy level without unbounded requests.

        ``limit`` remains the requested batch size, but every HTTP request is
        capped at ``_LAZY_BATCH_LIMIT``. The result is accumulated until the
        remote cursor is exhausted or the bounded discovery budget is reached.
        In the latter case the cursor from the last response is returned so a
        caller can continue instead of silently losing documents.
        """
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")

        # Allow per-project overrides while keeping the module-level constants as
        # the historical defaults (tests monkeypatch those constants directly).
        max_items = self.options.lazy_max_items or _LAZY_MAX_ITEMS
        batch_cap = self.options.lazy_batch_limit or _LAZY_BATCH_LIMIT

        items: list[dict[str, Any]] = []
        current_cursor = cursor
        request_limit = min(limit, batch_cap)

        while True:
            _check_token(token)
            remaining = max_items - len(items)
            if remaining <= 0:
                break
            batch_limit = min(request_limit, remaining)
            page_cursor = current_cursor
            payload = self._lazy_request(
                container_id,
                lambda client, page_cursor=page_cursor, batch_limit=batch_limit: fetch(
                    client,
                    page_cursor,
                    batch_limit,
                ),
            )
            _check_token(token)
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise TypeError("A resposta lazy do Confluence não possui results válido.")
            items.extend(results)

            next_cursor = payload.get("next_cursor")
            if not next_cursor or not results or len(items) >= max_items:
                return items, str(next_cursor) if next_cursor else None
            if str(next_cursor) == str(current_cursor or ""):
                return items, None
            current_cursor = str(next_cursor)

        return items, None

    def list_root_documents(
        self,
        container_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        etag: str | None = None,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[DocumentMetadata]:
        del etag
        raw_items, next_cursor = self._collect_lazy_pages(
            container_id,
            lambda client, page_cursor, page_limit: client.list_root_pages(
                cursor=page_cursor, limit=page_limit
            ),
            cursor=cursor,
            limit=limit,
            token=token,
        )
        items = tuple(
            self._browser_metadata(page, container_id, parent_id=None)
            for page in raw_items
        )
        return DiscoveryPage(
            items=items,
            cursor=cursor,
            next_cursor=next_cursor,
        )

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        etag: str | None = None,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[DocumentMetadata]:
        del etag
        raw_items, next_cursor = self._collect_lazy_pages(
            container_id,
            lambda client, page_cursor, page_limit: client.list_child_pages(
                parent_id, cursor=page_cursor, limit=page_limit
            ),
            cursor=cursor,
            limit=limit,
            token=token,
        )
        items = tuple(
            self._browser_metadata(page, container_id, parent_id=parent_id)
            for page in raw_items
        )
        return DiscoveryPage(
            items=items,
            cursor=cursor,
            next_cursor=next_cursor,
        )

    def search_documents(
        self,
        container_id: str | None,
        query: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        etag: str | None = None,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[SearchResult]:
        del etag
        target = container_id or self.source.space_key
        if not target:
            raise ValueError("container_id é obrigatório para a busca Confluence.")
        _check_token(token)
        payload = self._lazy_request(
            target,
            lambda client: client.search_pages(
                query,
                container_id=target,
                cursor=cursor,
                limit=limit,
            ),
        )
        _check_token(token)
        return DiscoveryPage(
            items=tuple(
                SearchResult(document=self._browser_metadata(page, target))
                for page in payload["results"]
            ),
            cursor=cursor,
            next_cursor=payload.get("next_cursor"),
            etag=payload.get("etag"),
        )

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do Confluence deve ser um objeto JSON.")
        return ConfluenceDocumentParser(
            self.source,
            self.markdown_options,
        ).parse(raw_document)

    def _metadata(
        self, page: dict[str, Any], container_id: str
    ) -> KnowledgeDocumentMetadata:
        ancestors = page.get("ancestors", []) or []
        titles = [str(item.get("title") or "") for item in ancestors if item.get("title")]
        parent_id = str(ancestors[-1].get("id")) if ancestors else None
        title = str(page.get("title") or "Sem título")
        version = page.get("version") or {}
        return KnowledgeDocumentMetadata(
            id=str(page.get("id", "")),
            container_id=container_id,
            parent_id=parent_id,
            title=title,
            original_url=ConfluenceClient.source_url(self.source.base_url, page),
            updated_at=_datetime(version.get("when")),
            has_children=False,
            document_type=str(page.get("type") or "page"),
            path=[*titles, title],
            metadata={
                "confluence_version": version.get("number"),
                "space_key": container_id,
                "space_name": (page.get("space") or {}).get("name", ""),
                "ancestors": ancestors,
                "visibility": self._explicit_visibility(page).value,
                "provider_ordered": True,
            },
        )

    def _browser_metadata(
        self,
        page: dict[str, Any],
        container_id: str,
        *,
        parent_id: str | None | object = _UNSET,
    ) -> DocumentMetadata:
        ancestors = page.get("ancestors") or []
        titles = tuple(
            str(item.get("title") or "") for item in ancestors if item.get("title")
        )
        inferred_parent = str(ancestors[-1].get("id")) if ancestors else None
        if parent_id is _UNSET:
            effective_parent = inferred_parent
        elif parent_id is None:
            effective_parent = None
        else:
            effective_parent = str(parent_id)
        title = str(page.get("title") or "Sem título")
        version = page.get("version") or {}
        visibility = self._explicit_visibility(page)
        return DocumentMetadata(
            source_id=self.source.id,
            container_id=container_id,
            id=str(page.get("id", "")),
            title=title,
            parent_id=effective_parent,
            original_url=ConfluenceClient.source_url(self.source.base_url, page),
            updated_at=_datetime(version.get("when")),
            etag=str(page.get("etag")) if page.get("etag") is not None else None,
            has_children=self._explicit_has_children(page),
            document_type=str(page.get("type") or "page"),
            path=(*titles, title),
            visibility=visibility,
            metadata=self._discovery_metadata(page, container_id, visibility),
        )

    @staticmethod
    def _explicit_visibility(page: dict[str, Any]) -> Visibility:
        for key in ("visibility", "access", "permission"):
            value = page.get(key)
            if value is not None and not isinstance(value, (dict, list)):
                parsed = Visibility.parse(value)
                if parsed is not Visibility.UNKNOWN:
                    return parsed

        metadata = page.get("metadata") or {}
        if isinstance(metadata, dict):
            for key in ("visibility", "access", "permission"):
                value = metadata.get(key)
                if value is not None and not isinstance(value, (dict, list)):
                    parsed = Visibility.parse(value)
                    if parsed is not Visibility.UNKNOWN:
                        return parsed

        for payload in (page.get("restrictions"), metadata.get("restrictions")):
            detected = ConfluenceRestConnector._visibility_from_restriction_payload(payload)
            if detected is not None:
                return detected
            if not isinstance(payload, dict):
                continue
            read = payload.get("read") or payload.get("view")
            if not isinstance(read, dict):
                continue
            details = read.get("restrictions", read)
            if not isinstance(details, dict):
                continue
            results = details.get("results")
            if isinstance(results, list):
                return Visibility.PRIVATE if results else Visibility.PUBLIC
            users = details.get("user")
            groups = details.get("group")
            user_res = users.get("results") if isinstance(users, dict) else (users if isinstance(users, list) else None)
            group_res = groups.get("results") if isinstance(groups, dict) else (groups if isinstance(groups, list) else None)
            has_user_restr = isinstance(user_res, list) and len(user_res) > 0
            has_group_restr = isinstance(group_res, list) and len(group_res) > 0
            if has_user_restr or has_group_restr:
                return Visibility.PRIVATE
            if user_res is not None or group_res is not None:
                return Visibility.PUBLIC

        if isinstance(page.get("public"), bool):
            return Visibility.PUBLIC if page["public"] else Visibility.PRIVATE
        if page.get("anonymous_access") is True:
            return Visibility.PUBLIC
        return Visibility.UNKNOWN

    @staticmethod
    def _visibility_from_restriction_payload(payload: object) -> Visibility | None:
        if not isinstance(payload, dict):
            return None
        for operation in ("read", "view"):
            read = payload.get(operation)
            if not isinstance(read, dict):
                continue
            details = read.get("restrictions", read)
            if isinstance(details, list):
                return Visibility.PRIVATE if details else Visibility.PUBLIC
            if not isinstance(details, dict):
                continue
            result_items = details.get("results")
            if isinstance(result_items, list):
                return Visibility.PRIVATE if result_items else Visibility.PUBLIC
            nested_items = details.get("restrictions")
            if isinstance(nested_items, list):
                return Visibility.PRIVATE if nested_items else Visibility.PUBLIC
            subjects_present = False
            for subject in (details.get("user"), details.get("group")):
                if subject is None:
                    continue
                subjects_present = True
                if isinstance(subject, dict):
                    subject = subject.get("results")
                if isinstance(subject, list) and subject:
                    return Visibility.PRIVATE
            if subjects_present:
                return Visibility.PUBLIC
        return None


    @staticmethod
    def _explicit_has_children(page: dict[str, Any]) -> bool:
        for key in ("has_children", "hasChildren"):
            value = page.get(key)
            if isinstance(value, bool):
                return value
        children = page.get("children")
        if isinstance(children, dict) and isinstance(children.get("size"), int):
            return children["size"] > 0
        links = page.get("_links") or {}
        return isinstance(links, dict) and isinstance(links.get("child"), str)

    @classmethod
    def _discovery_metadata(
        cls, page: dict[str, Any], container_id: str, visibility: Visibility
    ) -> dict[str, Any]:
        return {
            "confluence_version": (page.get("version") or {}).get("number"),
            "space_key": container_id,
            "space_name": (page.get("space") or {}).get("name", ""),
            "ancestors": page.get("ancestors", []) or [],
            "visibility": visibility.value,
            "visibility_evidence": visibility is not Visibility.UNKNOWN,
        }

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        close = getattr(self.client, "close", None)
        if callable(close):
            close()
        self.secret = ""


def _check_token(token: CancellationLike | None) -> None:
    if token is not None:
        token.check()
