from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlsplit

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
from ..source_discovery import SourceDiscoveryService
from .base import KnowledgeSourceConnector
from .generic_web import SafeStaticHttpClient, StaticHtmlParser, normalize_web_url


class GenericDocsConnector(KnowledgeSourceConnector):
    """Universal documentation connector for static doc frameworks, sitemaps, and llms.txt."""

    SOURCE_TYPE = "generic_docs"

    def __init__(
        self,
        source: SourceConfig,
        options: ExtractionOptions,
        *,
        secret: str = "",
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        client: SafeStaticHttpClient | None = None,
        markdown_options: MarkdownOptions | None = None,
    ) -> None:
        del secret, markdown_options
        self.source = source
        self.options = options
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.client = client or SafeStaticHttpClient(options, token=self.token, log=self.log)
        self.parser = StaticHtmlParser()
        self.url = normalize_web_url(source.base_url)
        self._discovery_cache: dict[str, Any] = {}
        self._url_by_doc_id: dict[str, str] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Documentação Web",
            base_url=self.url,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_updated_at=True,
            supports_sitemap=True,
            supports_llms_txt=True,
            supports_crawler=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        discovery_svc = SourceDiscoveryService(self.options, token=self.token)
        try:
            res = discovery_svc.discover(self.url, deep_crawl=False, max_pages=10)
            return {
                "url": self.url,
                "strategy": res.strategy.value,
                "framework": res.framework or "web",
                "llms_txt": res.llms_txt_url,
                "sitemap": res.sitemap_url,
                "resources_found": len(res.resources),
            }
        finally:
            discovery_svc.close()

    def list_containers(self) -> list[KnowledgeContainer]:
        host = urlsplit(self.url).hostname or "docs"
        return [
            KnowledgeContainer(
                id=host,
                key=host,
                name=f"Documentação ({host})",
                container_type="documentation_site",
                source_type=self.SOURCE_TYPE,
            )
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        discovery_svc = SourceDiscoveryService(self.options, token=self.token)
        documents: list[KnowledgeDocumentMetadata] = []
        try:
            res = discovery_svc.discover(self.url, deep_crawl=True, max_pages=300)
            for item in res.resources:
                doc_id = hashlib.sha256(item.url.encode("utf-8")).hexdigest()
                self._url_by_doc_id[doc_id] = item.url
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=doc_id,
                        container_id=container_id,
                        title=item.title or item.url,
                        original_url=item.url,
                        path=[container_id, item.title or item.url],
                        metadata={"resource_type": item.resource_type, "depth": item.depth},
                    )
                )
        finally:
            discovery_svc.close()

        if not documents:
            doc_id = hashlib.sha256(self.url.encode("utf-8")).hexdigest()
            self._url_by_doc_id[doc_id] = self.url
            documents.append(
                KnowledgeDocumentMetadata(
                    id=doc_id,
                    container_id=container_id,
                    title=self.url,
                    original_url=self.url,
                )
            )

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        target_url = self._url_by_doc_id.get(document_id) or self.url
        final_url, _ctype, headers, body = self.client.get(target_url)

        # If it is llms.txt / text/plain
        if target_url.endswith(".txt") or "text/plain" in _ctype:
            content = normalize_markdown(body.decode("utf-8", errors="replace"))
            return KnowledgeDocument(
                id=document_id,
                container_id=container_id or "docs",
                title=f"llms.txt — {urlsplit(final_url).hostname}",
                content=content,
                original_url=final_url,
                source_type=self.SOURCE_TYPE,
                container_name=container_id or "Documentação",
                metadata={"raw_type": "llms_txt"},
            )

        doc = self.parser.parse(body, url=target_url, final_url=final_url, headers=headers)
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or doc.container_id,
            parent_id=doc.parent_id,
            title=doc.title,
            content=doc.content,
            original_url=final_url,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            etag=doc.etag,
            source_type=self.SOURCE_TYPE,
            container_name=container_id or doc.container_name,
            path=doc.path,
            metadata=doc.metadata,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Generic Docs deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.client.close()
