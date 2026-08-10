from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .models import ManifestDocument


class ManifestIndex:
    """SQLite sidecar index for fast lookup of large manifests.

    The JSON manifesto remains the portable source of truth. This index is
    rebuilt atomically from it and can always be discarded and recreated.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def rebuild(self, document: ManifestDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(
            prefix=f".{self.path.stem}.", suffix=".sqlite3", dir=self.path.parent
        )
        os.close(fd)
        temporary = Path(raw_path)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(temporary)
            with connection:
                connection.execute("PRAGMA journal_mode = DELETE")
                connection.execute(
                    """
                    CREATE TABLE manifest_entries (
                        document_key TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        source_type TEXT NOT NULL,
                        container_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        updated_at TEXT,
                        etag TEXT,
                        content_hash TEXT,
                        active INTEGER NOT NULL,
                        selected INTEGER NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                connection.executemany(
                    """
                    INSERT INTO manifest_entries (
                        document_key, source_id, source_type, container_id,
                        document_id, title, updated_at, etag, content_hash,
                        active, selected, payload
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            entry.document_key,
                            entry.source_id,
                            entry.source_type,
                            entry.container_id,
                            entry.document_id or entry.page_id,
                            entry.title,
                            entry.updated_at,
                            entry.etag,
                            entry.content_hash,
                            int(entry.active),
                            int(entry.selected),
                            json.dumps(entry.model_dump(mode="json"), ensure_ascii=False),
                        )
                        for entry in document.entries
                    ],
                )
                connection.execute(
                    "CREATE INDEX idx_manifest_source_container "
                    "ON manifest_entries(source_id, container_id)"
                )
                connection.execute(
                    "CREATE INDEX idx_manifest_updated "
                    "ON manifest_entries(updated_at)"
                )
                connection.commit()
            connection.close()
            os.replace(temporary, self.path)
        finally:
            if connection is not None:
                connection.close()
            temporary.unlink(missing_ok=True)

    def get(self, document_key: str) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        connection = sqlite3.connect(self.path)
        try:
            row = connection.execute(
                "SELECT payload FROM manifest_entries WHERE document_key = ?",
                (document_key,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return json.loads(str(row[0]))
