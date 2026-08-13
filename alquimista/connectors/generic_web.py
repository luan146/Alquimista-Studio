from __future__ import annotations

import hashlib
import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

from ..errors import InvalidResponseError
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


def normalize_web_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Generic Web aceita somente URLs HTTPS públicas sem credenciais.")
    host = parsed.hostname.lower()
    port = parsed.port
    if not _is_ip(host) and "." not in host:
        raise ValueError("O host do Generic Web deve ser público e qualificado.")
    if _is_ip(host) and not ipaddress.ip_address(host).is_global:
        raise ValueError("O host do Generic Web não é global.")
    netloc = host if port in (None, 443) else f"{host}:{port}"
    return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _validate_host(host: str) -> None:
    if not host or host == "localhost" or "." not in host:
        raise ValueError("Destino local ou host sem domínio recusado.")
    addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(item).is_global for item in addresses):
        raise ValueError("O destino resolve para um endereço não global.")


class SafeStaticHttpClient:
    def __init__(self, options: ExtractionOptions, *, token: CancellationToken, log: LogCallback) -> None:
        self.options, self.token, self.log = options, token, log
        self.session = requests.Session()
        self.session.trust_env = False

    def get(self, url: str) -> tuple[str, str, dict[str, str], bytes]:
        current = normalize_web_url(url)
        for _ in range(6):
            self.token.check()
            parsed = urlsplit(current)
            _validate_host(parsed.hostname or "")
            response = self.session.get(current, allow_redirects=False, timeout=(self.options.connect_timeout_seconds, self.options.timeout_seconds), stream=True, headers={"Accept": "text/html,application/xhtml+xml"})
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location: raise InvalidResponseError("Redirect sem destino.")
                current = normalize_web_url(urljoin(current, location))
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise InvalidResponseError("Generic Web aceita somente HTML/XHTML.")
            body = response.content
            if len(body) > 5 * 1024 * 1024:
                raise InvalidResponseError("A resposta do Generic Web excedeu 5 MiB.")
            return current, content_type, dict(response.headers), body
        raise InvalidResponseError("Número máximo de redirects excedido.")

    def close(self) -> None:
        self.session.close()


class StaticHtmlParser:
    def parse(self, html: bytes, *, url: str, final_url: str, headers: dict[str, str]) -> KnowledgeDocument:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template", "form"]): tag.decompose()
        main = soup.find_all("main")
        article = soup.find_all("article")
        root = main[0] if len(main) == 1 else article[0] if len(article) == 1 else soup.body or soup
        title = str((soup.title.string if soup.title and soup.title.string else "") or "").strip()
        heading = root.find("h1")
        title = title or (heading.get_text(" ", strip=True) if heading is not None else urlsplit(final_url).hostname or "Página Web")
        for tag in root.find_all(["a", "img"]):
            attr = "href" if tag.name == "a" else "src"
            value = tag.get(attr)
            if isinstance(value, str) and value:
                tag[attr] = urljoin(final_url, value)
        content = normalize_markdown(markdownify(str(root), heading_style="ATX", bullets="-"))
        doc_id = hashlib.sha256(normalize_web_url(url).encode()).hexdigest()
        canonical_tag = soup.find("link", rel="canonical")
        canonical = canonical_tag.get("href") if canonical_tag is not None else ""
        return KnowledgeDocument(id=doc_id, container_id=urlsplit(final_url).hostname or "", title=title, content=content, original_url=final_url, source_type="generic_web", container_name=urlsplit(final_url).hostname or "", metadata={"configured_url": url, "final_url": final_url, "canonical": str(canonical or ""), "etag": headers.get("ETag"), "last_modified": headers.get("Last-Modified")})


class GenericWebConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "generic_web"
    def __init__(self, source: SourceConfig, options: ExtractionOptions, *, secret: str = "", token: CancellationToken | None = None, log: LogCallback | None = None, client: SafeStaticHttpClient | None = None, markdown_options: MarkdownOptions | None = None) -> None:
        del secret, markdown_options
        self.source, self.options = source, options
        self.token, self.log = token or CancellationToken(), log or (lambda _message: None)
        self.client = client or SafeStaticHttpClient(options, token=self.token, log=self.log)
        self.parser = StaticHtmlParser()
        self.url = normalize_web_url(source.base_url)
    def get_source_type(self) -> str: return self.SOURCE_TYPE
    def get_source(self) -> KnowledgeSource: return KnowledgeSource(id=self.source.id, source_type=self.SOURCE_TYPE, name=self.source.name, base_url=self.source.base_url)
    def get_capabilities(self) -> ConnectorCapabilities: return ConnectorCapabilities(supports_collections=True, supports_incremental_updates=True, supports_public_access=True, supports_updated_at=True)
    def validate_connection(self) -> dict[str, Any]: return {"url": self.url}
    def list_containers(self) -> list[KnowledgeContainer]:
        host = urlsplit(self.url).hostname or ""
        return [KnowledgeContainer(id=host, key=host, name=host, container_type="host", source_type=self.SOURCE_TYPE)]
    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        doc_id = hashlib.sha256(self.url.encode()).hexdigest()
        return [KnowledgeDocumentMetadata(id=doc_id, container_id=container_id, title=self.url, original_url=self.url)]
    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        expected = hashlib.sha256(self.url.encode()).hexdigest()
        if document_id != expected: raise InvalidResponseError("URL não pertence ao documento configurado.")
        final_url, _ctype, headers, body = self.client.get(self.url)
        return self.parser.parse(body, url=self.url, final_url=final_url, headers=headers)
    def close(self) -> None: self.client.close()
