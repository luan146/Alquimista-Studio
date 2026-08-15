"""Durable, metadata-only SQLite cache for lazy discovery."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .contracts import (
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
    SpaceMetadata,
)

_SENSITIVE_PARTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
    "content",
    "body",
    "html",
    "markdown",
    "raw",
)


def _key_part(value: str | None) -> str:
    return value or ""


def _query_key(query: str) -> str:
    normalized = " ".join(query.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _safe_metadata(value: object, *, depth: int = 0) -> object:
    """Keep cache payloads JSON-safe and drop likely secret/body fields."""
    if depth > 4:
        return None
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.casefold()
            if any(part in lowered for part in _SENSITIVE_PARTS):
                continue
            safe_value = _safe_metadata(item, depth=depth + 1)
            if safe_value is not None:
                result[key_text] = safe_value
        return result
    if isinstance(value, (list, tuple)):
        return [safe for item in value if (safe := _safe_metadata(item, depth=depth + 1)) is not None]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _safe_space(value: SpaceMetadata) -> dict[str, Any]:
    payload = value.to_dict()
    payload["metadata"] = _safe_metadata(value.metadata)
    return payload


def _safe_document(value: DocumentMetadata) -> dict[str, Any]:
    payload = value.to_dict()
    payload["metadata"] = _safe_metadata(value.metadata)
    return payload


def _safe_search(value: SearchResult) -> dict[str, Any]:
    return {
        "document": _safe_document(value.document),
        "match_kind": value.match_kind,
        "score": value.score,
    }


class BrowserCache:
    """SQLite cache independent from the extraction manifest index.

    Only discovery metadata is persisted.  ``scope`` separates public and
    authenticated discovery snapshots without persisting authentication
    material; callers should pass a stable, non-secret label such as
    ``"public"`` or ``"authenticated"``.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path: Path, *, clock: Callable[[], float] | None = None) -> None:
        self.path = Path(path)
        self._clock = clock or time.time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def __enter__(self) -> "BrowserCache":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the cache handle.

        Connections are intentionally short-lived per operation, so this is a
        no-op today and remains a stable lifecycle hook for callers.
        """

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        connection = self._connection()
        try:
            with connection:
                connection.execute("CREATE TABLE IF NOT EXISTS cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS containers (
                        source_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        container_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        etag TEXT,
                        fetched_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (source_id, scope, container_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS container_pages (
                        source_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        cursor_key TEXT NOT NULL,
                        container_ids TEXT NOT NULL,
                        next_cursor TEXT,
                        etag TEXT,
                        fetched_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (source_id, scope, cursor_key)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        source_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        container_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        etag TEXT,
                        fetched_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (source_id, scope, container_id, document_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_pages (
                        source_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        container_id TEXT NOT NULL,
                        parent_key TEXT NOT NULL,
                        cursor_key TEXT NOT NULL,
                        document_ids TEXT NOT NULL,
                        next_cursor TEXT,
                        etag TEXT,
                        fetched_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (source_id, scope, container_id, parent_key, cursor_key)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_pages (
                        source_id TEXT NOT NULL,
                        scope TEXT NOT NULL,
                        container_key TEXT NOT NULL,
                        query_hash TEXT NOT NULL,
                        cursor_key TEXT NOT NULL,
                        results TEXT NOT NULL,
                        next_cursor TEXT,
                        etag TEXT,
                        fetched_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (source_id, scope, container_key, query_hash, cursor_key)
                    )
                    """
                )
                connection.execute(
                    "INSERT OR REPLACE INTO cache_meta(key, value) VALUES ('schema_version', ?)",
                    (str(self.SCHEMA_VERSION),),
                )
        finally:
            connection.close()

    @staticmethod
    def _expiry(now: float, ttl_seconds: float) -> float:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds não pode ser negativo")
        return now + ttl_seconds

    def _page_available(self, expires_at: float, *, allow_stale: bool) -> bool:
        return allow_stale or self._clock() < expires_at

    def put_containers(
        self,
        source_id: str,
        items: Iterable[SpaceMetadata],
        *,
        scope: str = "default",
        cursor: str | None = None,
        next_cursor: str | None = None,
        etag: str | None = None,
        ttl_seconds: float = 3600,
    ) -> None:
        values = tuple(items)
        now = self._clock()
        expires = self._expiry(now, ttl_seconds)
        connection = self._connection()
        try:
            with connection:
                for item in values:
                    if item.source_id != source_id:
                        raise ValueError("o source_id do contêiner não corresponde ao cache")
                    connection.execute(
                        """
                        INSERT INTO containers(source_id, scope, container_id, payload, etag, fetched_at, expires_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_id, scope, container_id) DO UPDATE SET
                            payload=excluded.payload, etag=excluded.etag,
                            fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
                        """,
                        (source_id, scope, item.id, _json(_safe_space(item)), item.etag or etag, now, expires),
                    )
                connection.execute(
                    """
                    INSERT INTO container_pages(
                        source_id, scope, cursor_key, container_ids, next_cursor, etag, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, scope, cursor_key) DO UPDATE SET
                        container_ids=excluded.container_ids, next_cursor=excluded.next_cursor,
                        etag=excluded.etag, fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
                    """,
                    (source_id, scope, _key_part(cursor), _json([item.id for item in values]), next_cursor, etag, now, expires),
                )
        finally:
            connection.close()

    def get_containers(
        self,
        source_id: str,
        *,
        scope: str = "default",
        cursor: str | None = None,
        allow_stale: bool = False,
    ) -> DiscoveryPage[SpaceMetadata] | None:
        connection = self._connection()
        try:
            page = connection.execute(
                """
                SELECT * FROM container_pages
                WHERE source_id = ? AND scope = ? AND cursor_key = ?
                """,
                (source_id, scope, _key_part(cursor)),
            ).fetchone()
            if page is None or not self._page_available(float(page["expires_at"]), allow_stale=allow_stale):
                return None
            ids = json.loads(str(page["container_ids"]))
            if not ids:
                rows = []
            else:
                placeholders = ",".join("?" for _ in ids)
                cursor_res = connection.execute(
                    f"SELECT container_id, payload FROM containers WHERE source_id = ? AND scope = ? AND container_id IN ({placeholders})",
                    (source_id, scope, *[str(cid) for cid in ids]),
                )
                payload_by_id = {str(row["container_id"]): str(row["payload"]) for row in cursor_res.fetchall()}
                rows = [
                    SpaceMetadata.from_dict(json.loads(payload_by_id[str(cid)]))
                    for cid in ids
                    if str(cid) in payload_by_id
                ]
            return DiscoveryPage(
                items=tuple(rows),
                cursor=cursor,
                next_cursor=page["next_cursor"],
                etag=page["etag"],
                from_cache=True,
                stale=self._clock() >= float(page["expires_at"]),
            )
        finally:
            connection.close()

    def put_documents(
        self,
        source_id: str,
        container_id: str,
        items: Iterable[DocumentMetadata],
        *,
        scope: str = "default",
        parent_id: str | None = None,
        cursor: str | None = None,
        next_cursor: str | None = None,
        etag: str | None = None,
        ttl_seconds: float = 3600,
    ) -> None:
        values = tuple(items)
        now = self._clock()
        expires = self._expiry(now, ttl_seconds)
        connection = self._connection()
        try:
            with connection:
                for item in values:
                    if item.source_id != source_id or item.container_id != container_id:
                        raise ValueError("a chave do documento não corresponde ao cache")
                    connection.execute(
                        """
                        INSERT INTO documents(
                            source_id, scope, container_id, document_id, payload, etag, fetched_at, expires_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(source_id, scope, container_id, document_id) DO UPDATE SET
                            payload=excluded.payload, etag=excluded.etag,
                            fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
                        """,
                        (source_id, scope, container_id, item.id, _json(_safe_document(item)), item.etag or etag, now, expires),
                    )
                connection.execute(
                    """
                    INSERT INTO document_pages(
                        source_id, scope, container_id, parent_key, cursor_key, document_ids,
                        next_cursor, etag, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, scope, container_id, parent_key, cursor_key) DO UPDATE SET
                        document_ids=excluded.document_ids, next_cursor=excluded.next_cursor,
                        etag=excluded.etag, fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
                    """,
                    (
                        source_id,
                        scope,
                        container_id,
                        _key_part(parent_id),
                        _key_part(cursor),
                        _json([item.id for item in values]),
                        next_cursor,
                        etag,
                        now,
                        expires,
                    ),
                )
        finally:
            connection.close()

    def get_documents(
        self,
        source_id: str,
        container_id: str,
        *,
        scope: str = "default",
        parent_id: str | None = None,
        cursor: str | None = None,
        allow_stale: bool = False,
    ) -> DiscoveryPage[DocumentMetadata] | None:
        connection = self._connection()
        try:
            page = connection.execute(
                """
                SELECT * FROM document_pages
                WHERE source_id = ? AND scope = ? AND container_id = ?
                  AND parent_key = ? AND cursor_key = ?
                """,
                (source_id, scope, container_id, _key_part(parent_id), _key_part(cursor)),
            ).fetchone()
            if page is None or not self._page_available(float(page["expires_at"]), allow_stale=allow_stale):
                return None
            ids = json.loads(str(page["document_ids"]))
            if not ids:
                rows = []
            else:
                placeholders = ",".join("?" for _ in ids)
                cursor_res = connection.execute(
                    f"SELECT document_id, payload FROM documents WHERE source_id = ? AND scope = ? AND container_id = ? AND document_id IN ({placeholders})",
                    (source_id, scope, container_id, *[str(did) for did in ids]),
                )
                payload_by_id = {str(row["document_id"]): str(row["payload"]) for row in cursor_res.fetchall()}
                rows = [
                    DocumentMetadata.from_dict(json.loads(payload_by_id[str(did)]))
                    for did in ids
                    if str(did) in payload_by_id
                ]
            return DiscoveryPage(
                items=tuple(rows),
                cursor=cursor,
                next_cursor=page["next_cursor"],
                etag=page["etag"],
                from_cache=True,
                stale=self._clock() >= float(page["expires_at"]),
            )
        finally:
            connection.close()

    def put_search_results(
        self,
        source_id: str,
        query: str,
        items: Iterable[SearchResult],
        *,
        scope: str = "default",
        container_id: str | None = None,
        cursor: str | None = None,
        next_cursor: str | None = None,
        etag: str | None = None,
        ttl_seconds: float = 3600,
    ) -> None:
        values = tuple(items)
        now = self._clock()
        expires = self._expiry(now, ttl_seconds)
        connection = self._connection()
        try:
            with connection:
                for result in values:
                    document = result.document
                    if document.source_id != source_id:
                        raise ValueError("o source_id do resultado não corresponde ao cache")
                    self._put_document_row(connection, document, scope=scope, now=now, expires=expires)
                connection.execute(
                    """
                    INSERT INTO search_pages(
                        source_id, scope, container_key, query_hash, cursor_key, results,
                        next_cursor, etag, fetched_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, scope, container_key, query_hash, cursor_key) DO UPDATE SET
                        results=excluded.results, next_cursor=excluded.next_cursor,
                        etag=excluded.etag, fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
                    """,
                    (
                        source_id,
                        scope,
                        _key_part(container_id),
                        _query_key(query),
                        _key_part(cursor),
                        _json([_safe_search(item) for item in values]),
                        next_cursor,
                        etag,
                        now,
                        expires,
                    ),
                )
        finally:
            connection.close()

    @staticmethod
    def _put_document_row(
        connection: sqlite3.Connection,
        item: DocumentMetadata,
        *,
        scope: str,
        now: float,
        expires: float,
    ) -> None:
        connection.execute(
            """
            INSERT INTO documents(
                source_id, scope, container_id, document_id, payload, etag, fetched_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, scope, container_id, document_id) DO UPDATE SET
                payload=excluded.payload, etag=excluded.etag,
                fetched_at=excluded.fetched_at, expires_at=excluded.expires_at
            """,
            (item.source_id, scope, item.container_id, item.id, _json(_safe_document(item)), item.etag, now, expires),
        )

    def get_search_results(
        self,
        source_id: str,
        query: str,
        *,
        scope: str = "default",
        container_id: str | None = None,
        cursor: str | None = None,
        allow_stale: bool = False,
    ) -> DiscoveryPage[SearchResult] | None:
        connection = self._connection()
        try:
            page = connection.execute(
                """
                SELECT * FROM search_pages
                WHERE source_id = ? AND scope = ? AND container_key = ?
                  AND query_hash = ? AND cursor_key = ?
                """,
                (source_id, scope, _key_part(container_id), _query_key(query), _key_part(cursor)),
            ).fetchone()
            if page is None or not self._page_available(float(page["expires_at"]), allow_stale=allow_stale):
                return None
            raw_items = json.loads(str(page["results"]))
            items = tuple(
                SearchResult(
                    document=DocumentMetadata.from_dict(item["document"]),
                    match_kind=str(item.get("match_kind") or "title"),
                    score=float(item["score"]) if item.get("score") is not None else None,
                )
                for item in raw_items
            )
            return DiscoveryPage(
                items=items,
                cursor=cursor,
                next_cursor=page["next_cursor"],
                etag=page["etag"],
                from_cache=True,
                stale=self._clock() >= float(page["expires_at"]),
            )
        finally:
            connection.close()

    def delete_expired(self) -> int:
        """Remove expired discovery rows; this never touches extraction data."""
        now = self._clock()
        connection = self._connection()
        try:
            with connection:
                total = 0
                for table in ("containers", "container_pages", "documents", "document_pages", "search_pages"):
                    cursor = connection.execute(f"DELETE FROM {table} WHERE expires_at <= ?", (now,))
                    total += cursor.rowcount
                return total
        finally:
            connection.close()

    def purge_source(self, source_id: str, *, scope: str | None = None) -> int:
        """Remove discovery snapshots for a source.

        Authenticated snapshots are metadata-only, but titles, URLs and
        visibility can still reveal private information.  Purging is therefore
        intentionally scoped to the source (and optionally one identity scope)
        and covers both item and page tables atomically.
        """
        if not str(source_id).strip():
            raise ValueError("source_id é obrigatório")
        connection = self._connection()
        try:
            with connection:
                where = "source_id = ?"
                params: list[object] = [source_id]
                if scope is not None:
                    where += " AND scope = ?"
                    params.append(scope)
                total = 0
                for table in ("containers", "container_pages", "documents", "document_pages", "search_pages"):
                    cursor = connection.execute(f"DELETE FROM {table} WHERE {where}", params)
                    total += cursor.rowcount
                return total
        finally:
            connection.close()
