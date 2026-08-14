from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from ..errors import AuthenticationError
from ..markdown import normalize_markdown
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
from .http import ApiHttpClient


def _datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


class SliteConnector(KnowledgeSourceConnector):
    """Connector for Slite Channels and Notes/Docs API."""

    SOURCE_TYPE = "slite_api"
    BASE_URL = "https://api.slite.com/v1"

    def __init__(
        self,
        source: SourceConfig,
        options: ExtractionOptions,
        *,
        secret: str = "",
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        client: ApiHttpClient | None = None,
        markdown_options: MarkdownOptions | None = None,
    ) -> None:
        del markdown_options
        if not secret.strip():
            raise AuthenticationError("Informe uma API Key do Slite.")
        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        self.client = client or ApiHttpClient(
            self.BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers={
                "x-slite-api-key": secret,
                "Accept": "application/json",
            },
        )
        self._channels: dict[str, KnowledgeContainer] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Slite",
            base_url=self.BASE_URL,
            connector_version="v1",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_bearer_token=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json("channels")
        channels = (
            data.get("channels")
            or (data if isinstance(data, list) else [])
        ) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        return {
            "channels_count": len(channels),
            "auth": "Slite API Key",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        data = self.client.get_json("channels")
        channels = (
            data.get("channels")
            or (data if isinstance(data, list) else [])
        ) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        containers: list[KnowledgeContainer] = []
        for ch in channels:
            cid = str(ch.get("id"))
            name = str(ch.get("name") or cid)
            c = KnowledgeContainer(
                id=cid,
                key=cid,
                name=name,
                description=str(ch.get("description") or ""),
                container_type="channel",
                source_type=self.SOURCE_TYPE,
            )
            self._channels[cid] = c
            containers.append(c)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        try:
            data = self.client.get_json(f"channels/{quote(container_id, safe='')}/notes")
            notes = (
                data.get("notes")
                or (data if isinstance(data, list) else [])
            ) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            ch = self._channels.get(container_id)
            ch_name = ch.name if ch else container_id
            for note in notes:
                nid = str(note.get("id"))
                title = str(note.get("title") or f"Nota #{nid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=nid,
                        container_id=container_id,
                        title=title,
                        created_at=_datetime(note.get("created_at")),
                        updated_at=_datetime(note.get("updated_at")),
                        document_type="note",
                        path=[ch_name, title],
                        metadata=note,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar notas no canal {container_id} do Slite: {exc}")
        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        data = self.client.get_json(f"notes/{quote(document_id, safe='')}")
        raw_note = data.get("note") if isinstance(data, dict) and "note" in data else data
        note: dict[str, Any] = raw_note if isinstance(raw_note, dict) else {}
        title = str(note.get("title") or f"Nota #{document_id}")
        markdown_body = str(note.get("markdown") or note.get("body") or "")
        content = normalize_markdown(markdown_body)

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "ch-1",
            title=title,
            content=content,
            original_url=str(note.get("url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "Slite Notes",
            created_at=_datetime(note.get("created_at")),
            updated_at=_datetime(note.get("updated_at")),
            path=[container_id or "Slite Notes", title],
            metadata=note,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Slite deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

