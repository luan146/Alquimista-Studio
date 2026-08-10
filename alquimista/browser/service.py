"""Synchronous cache-first lazy discovery service, independent from Qt."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from threading import Lock, RLock
from typing import TypeVar

from .cache import BrowserCache
from .contracts import (
    CancellationLike,
    DiscoveryAdapter,
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
    SpaceMetadata,
)


class CacheMissError(RuntimeError):
    """Raised when an adapter returns not-modified but no local page exists."""


_T = TypeVar("_T")


class LazyDiscoveryService:
    """Coordinate lazy provider calls with an optional durable metadata cache.

    Methods are deliberately synchronous so a caller can place them in its own
    thread or process.  This class never imports Qt and never stores adapter
    instances, credentials, or complete document content in SQLite.
    """

    def __init__(
        self,
        source_id: str,
        adapter: DiscoveryAdapter,
        *,
        cache: BrowserCache | None = None,
        cache_scope: str = "default",
        ttl_seconds: float = 3600,
        stale_if_error: bool = False,
    ) -> None:
        if not source_id.strip():
            raise ValueError("source_id é obrigatório")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds não pode ser negativo")
        if not cache_scope.strip():
            raise ValueError("cache_scope é obrigatório")
        self.source_id = source_id
        self.adapter = adapter
        self.cache = cache
        self.cache_scope = cache_scope
        self.ttl_seconds = ttl_seconds
        self.stale_if_error = stale_if_error
        self._lock_guard = RLock()
        self._load_locks: dict[tuple[object, ...], Lock] = {}

    @property
    def cache_enabled(self) -> bool:
        """Whether this service can reuse results across calls/restarts."""
        return self.cache is not None

    def list_containers(
        self,
        *,
        cursor: str | None = None,
        limit: int = 100,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[SpaceMetadata]:
        self._validate_limit(limit)
        return self._load(
            ("containers", cursor, limit),
            token,
            cache_get=lambda allow_stale: self.cache.get_containers(
                self.source_id, scope=self.cache_scope, cursor=cursor, allow_stale=allow_stale
            )
            if self.cache
            else None,
            fetch=lambda etag: self.adapter.list_containers(
                cursor=cursor, limit=limit, etag=etag, token=token
            ),
            cache_put=lambda page: self.cache.put_containers(
                self.source_id,
                page.items,
                scope=self.cache_scope,
                cursor=cursor,
                next_cursor=page.next_cursor,
                etag=page.etag,
                ttl_seconds=self.ttl_seconds,
            )
            if self.cache
            else None,
        )

    def list_root_documents(
        self,
        container_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[DocumentMetadata]:
        self._validate_limit(limit)
        if not container_id.strip():
            raise ValueError("container_id é obrigatório")
        return self._load(
            ("root", container_id, cursor, limit),
            token,
            cache_get=lambda allow_stale: self.cache.get_documents(
                self.source_id,
                container_id,
                scope=self.cache_scope,
                parent_id=None,
                cursor=cursor,
                allow_stale=allow_stale,
            )
            if self.cache
            else None,
            fetch=lambda etag: self.adapter.list_root_documents(
                container_id, cursor=cursor, limit=limit, etag=etag, token=token
            ),
            cache_put=lambda page: self.cache.put_documents(
                self.source_id,
                container_id,
                page.items,
                scope=self.cache_scope,
                parent_id=None,
                cursor=cursor,
                next_cursor=page.next_cursor,
                etag=page.etag,
                ttl_seconds=self.ttl_seconds,
            )
            if self.cache
            else None,
        )

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[DocumentMetadata]:
        self._validate_limit(limit)
        if not container_id.strip() or not parent_id.strip():
            raise ValueError("container_id e parent_id são obrigatórios")
        return self._load(
            ("children", container_id, parent_id, cursor, limit),
            token,
            cache_get=lambda allow_stale: self.cache.get_documents(
                self.source_id,
                container_id,
                scope=self.cache_scope,
                parent_id=parent_id,
                cursor=cursor,
                allow_stale=allow_stale,
            )
            if self.cache
            else None,
            fetch=lambda etag: self.adapter.list_document_children(
                container_id, parent_id, cursor=cursor, limit=limit, etag=etag, token=token
            ),
            cache_put=lambda page: self.cache.put_documents(
                self.source_id,
                container_id,
                page.items,
                scope=self.cache_scope,
                parent_id=parent_id,
                cursor=cursor,
                next_cursor=page.next_cursor,
                etag=page.etag,
                ttl_seconds=self.ttl_seconds,
            )
            if self.cache
            else None,
        )

    def search_documents(
        self,
        query: str,
        *,
        container_id: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[SearchResult]:
        self._validate_limit(limit)
        if not query.strip():
            raise ValueError("query não pode ser vazio")
        return self._load(
            ("search", container_id, " ".join(query.split()).casefold(), cursor, limit),
            token,
            cache_get=lambda allow_stale: self.cache.get_search_results(
                self.source_id,
                query,
                scope=self.cache_scope,
                container_id=container_id,
                cursor=cursor,
                allow_stale=allow_stale,
            )
            if self.cache
            else None,
            fetch=lambda etag: self.adapter.search_documents(
                container_id, query, cursor=cursor, limit=limit, etag=etag, token=token
            ),
            cache_put=lambda page: self.cache.put_search_results(
                self.source_id,
                query,
                page.items,
                scope=self.cache_scope,
                container_id=container_id,
                cursor=cursor,
                next_cursor=page.next_cursor,
                etag=page.etag,
                ttl_seconds=self.ttl_seconds,
            )
            if self.cache
            else None,
        )

    def _load(
        self,
        key: tuple[object, ...],
        token: CancellationLike | None,
        *,
        cache_get: Callable[[bool], DiscoveryPage[_T] | None],
        fetch: Callable[[str | None], DiscoveryPage[_T] | Sequence[_T]],
        cache_put: Callable[[DiscoveryPage[_T]], None] | None,
    ) -> DiscoveryPage[_T]:
        with self._lock_for(key):
            self._check(token)
            fresh = cache_get(False)
            if fresh is not None:
                return replace(fresh, from_cache=True, stale=False)
            stale = cache_get(True)
            self._check(token)
            try:
                page = self._coerce_page(fetch(stale.etag if stale else None))
                self._check(token)
            except Exception:
                if self.stale_if_error and stale is not None and not self._is_cancelled(token):
                    return replace(stale, from_cache=True, stale=True)
                raise
            if page.not_modified:
                if stale is None:
                    raise CacheMissError("O adaptador respondeu 304, mas não há cache local para reutilizar")
                page = DiscoveryPage(
                    items=stale.items,
                    cursor=stale.cursor,
                    next_cursor=stale.next_cursor,
                    etag=page.etag or stale.etag,
                )
            if cache_put is not None:
                cache_put(page)
            return page

    @staticmethod
    def _coerce_page(value: DiscoveryPage[_T] | Sequence[_T]) -> DiscoveryPage[_T]:
        if isinstance(value, DiscoveryPage):
            return value
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return DiscoveryPage(items=tuple(value))
        raise TypeError("o adaptador deve retornar DiscoveryPage ou uma sequência de metadados")

    def _lock_for(self, key: tuple[object, ...]) -> Lock:
        with self._lock_guard:
            return self._load_locks.setdefault(key, Lock())

    @staticmethod
    def _validate_limit(limit: int) -> None:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")

    @staticmethod
    def _check(token: CancellationLike | None) -> None:
        if token is not None:
            token.check()

    @staticmethod
    def _is_cancelled(token: CancellationLike | None) -> bool:
        return bool(getattr(token, "cancelled", False))
