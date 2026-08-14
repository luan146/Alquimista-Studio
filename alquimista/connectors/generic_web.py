from __future__ import annotations

import hashlib
import ipaddress
import re
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

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 ALQuimista/3.0"
)


def normalize_web_url(value: str) -> str:
    raw = value.strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Generic Web aceita somente URLs HTTP ou HTTPS válidas sem credenciais na URL.")
    host = parsed.hostname.lower()
    port = parsed.port
    is_default_port = (scheme == "https" and (port in (None, 443))) or (
        scheme == "http" and (port in (None, 80))
    )
    netloc = host if is_default_port else f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _validate_host(host: str) -> None:
    if not host or "." not in host:
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Destino sem host ou domínio válido recusado.")


class SafeStaticHttpClient:
    def __init__(
        self,
        options: ExtractionOptions,
        *,
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
    ) -> None:
        self.options = options
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )

    def get(self, url: str) -> tuple[str, str, dict[str, str], bytes]:
        current = normalize_web_url(url)
        for _ in range(10):
            self.token.check()
            parsed = urlsplit(current)
            _validate_host(parsed.hostname or "")
            response = self.session.get(
                current,
                allow_redirects=False,
                timeout=(self.options.connect_timeout_seconds, self.options.timeout_seconds),
                stream=True,
            )
            if response.is_redirect:
                location = response.headers.get("Location")
                if not location:
                    raise InvalidResponseError("Redirect sem destino.")
                current = normalize_web_url(urljoin(current, location))
                continue
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if content_type and content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise InvalidResponseError(f"Tipo de conteúdo não suportado: {content_type}")
            body = response.content
            if len(body) > 10 * 1024 * 1024:
                raise InvalidResponseError("A resposta do Generic Web excedeu 10 MiB.")
            return current, content_type or "text/html", dict(response.headers), body
        raise InvalidResponseError("Número máximo de redirects excedido.")

    def close(self) -> None:
        self.session.close()


class StaticHtmlParser:
    def parse(
        self, html: bytes, *, url: str, final_url: str, headers: dict[str, str]
    ) -> KnowledgeDocument:
        encoding = "utf-8"
        content_type_header = headers.get("Content-Type") or headers.get("content-type") or ""
        if "charset=" in content_type_header.lower():
            try:
                encoding = content_type_header.lower().split("charset=")[-1].split(";")[0].strip()
            except Exception:
                encoding = "utf-8"

        try:
            decoded_html = html.decode(encoding, errors="replace")
        except Exception:
            decoded_html = html.decode("utf-8", errors="replace")

        soup = BeautifulSoup(decoded_html, "html.parser")

        og_title = (
            soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "twitter:title"})
        )
        og_desc = (
            soup.find("meta", property="og:description")
            or soup.find("meta", attrs={"name": "description"})
        )
        canonical_tag = soup.find("link", rel="canonical")
        canonical = canonical_tag.get("href") if canonical_tag is not None else ""
        author_tag = soup.find("meta", attrs={"name": "author"})
        author = author_tag.get("content") if author_tag is not None else ""

        for tag in soup(
            [
                "script",
                "style",
                "noscript",
                "template",
                "form",
                "svg",
                "canvas",
                "iframe",
                "nav",
                "footer",
                "aside",
            ]
        ):
            tag.decompose()

        main_candidates = (
            soup.find_all("article")
            or soup.find_all("main")
            or soup.find_all("div", attrs={"role": "main"})
            or soup.find_all("div", class_=re.compile(r"(content|article|post|document|markdown-body)", re.I))
        )
        root = main_candidates[0] if main_candidates else soup.body or soup

        title = ""
        if og_title and isinstance(og_title.get("content"), str):
            title = str(og_title["content"]).strip()
        if not title:
            h1 = root.find("h1") or soup.find("h1")
            if h1 is not None:
                title = h1.get_text(" ", strip=True)
        if not title and soup.title and soup.title.string:
            title = str(soup.title.string).strip()
        if not title:
            title = urlsplit(final_url).hostname or "Página Web"

        for tag in root.find_all(["a", "img"]):
            attr = "href" if tag.name == "a" else "src"
            value = tag.get(attr)
            if isinstance(value, str) and value and not value.startswith(("javascript:", "mailto:", "#")):
                tag[attr] = urljoin(final_url, value)

        markdown_text = markdownify(str(root), heading_style="ATX", bullets="-")
        content = normalize_markdown(markdown_text)

        doc_id = hashlib.sha256(normalize_web_url(url).encode()).hexdigest()
        host = urlsplit(final_url).hostname or urlsplit(url).hostname or "web"

        metadata: dict[str, Any] = {
            "configured_url": url,
            "final_url": final_url,
            "canonical": str(canonical or ""),
            "etag": headers.get("ETag") or headers.get("etag"),
            "last_modified": headers.get("Last-Modified") or headers.get("last-modified"),
        }
        if og_desc and isinstance(og_desc.get("content"), str):
            metadata["description"] = str(og_desc["content"]).strip()
        if author:
            metadata["author"] = str(author).strip()

        return KnowledgeDocument(
            id=doc_id,
            container_id=host,
            title=title,
            content=content,
            original_url=final_url,
            source_type="generic_web",
            container_name=host,
            metadata=metadata,
        )


class GenericWebConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "generic_web"

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

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name,
            base_url=self.source.base_url,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        return {"url": self.url}

    def list_containers(self) -> list[KnowledgeContainer]:
        host = urlsplit(self.url).hostname or "web"
        return [
            KnowledgeContainer(
                id=host,
                key=host,
                name=host,
                container_type="host",
                source_type=self.SOURCE_TYPE,
            )
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        doc_id = hashlib.sha256(self.url.encode()).hexdigest()
        return [
            KnowledgeDocumentMetadata(
                id=doc_id,
                container_id=container_id,
                title=self.url,
                original_url=self.url,
            )
        ]

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        expected = hashlib.sha256(self.url.encode()).hexdigest()
        if document_id != expected:
            raise InvalidResponseError("URL não pertence ao documento configurado.")
        final_url, _ctype, headers, body = self.client.get(self.url)
        return self.parser.parse(body, url=self.url, final_url=final_url, headers=headers)

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do Generic Web deve ser um objeto JSON.")
        doc_id = str(raw_document.get("id") or hashlib.sha256(self.url.encode()).hexdigest())
        container_id = str(raw_document.get("container_id") or urlsplit(self.url).hostname or "")
        return KnowledgeDocument(
            id=doc_id,
            container_id=container_id,
            title=str(raw_document.get("title") or "Página Web"),
            content=normalize_markdown(str(raw_document.get("content") or raw_document.get("markdown") or "")),
            original_url=str(raw_document.get("original_url") or raw_document.get("url") or self.url),
            source_type=self.SOURCE_TYPE,
            container_name=container_id,
            metadata=dict(raw_document.get("metadata") or {}),
        )

    def close(self) -> None:
        self.client.close()

