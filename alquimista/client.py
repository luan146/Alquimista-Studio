from __future__ import annotations

import random
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .errors import (
    ApiConnectionError,
    ApiRateLimitError,
    AuthenticationError,
    InvalidResponseError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from .models import AuthMode, ExtractionOptions, SourceConfig
from .runtime import CancellationToken, LogCallback, RateLimiter
from .session_store import load_session
from .session_store import session_directory as _session_directory
from .session_store import session_path as _session_path


def session_directory() -> Path:
    return _session_directory()


def session_path(source_id: str) -> Path:
    return _session_path(source_id)


class ConfluenceClient:
    def __init__(
        self,
        source: SourceConfig,
        options: ExtractionOptions,
        *,
        secret: str = "",
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        session: requests.Session | None = None,
        sleep: Any = time.sleep,
        random_value: Any = random.random,
    ) -> None:
        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self._owns_session = session is None
        self.session = session or requests.Session()
        self._sleep = sleep
        self._random = random_value
        self.rate_limiter = RateLimiter(options.max_requests_per_second, self.token)
        self._configure_session()

    @property
    def base_url(self) -> str:
        return self.source.base_url.rstrip("/")

    def _request_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ApiConnectionError(
                f"A fonte “{self.source.name}” ({self.source.id}) não possui uma "
                f"base_url válida para o Confluence: {self.source.base_url or 'vazia'}. "
                "Informe uma URL completa, por exemplo https://example.com."
            )
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _configure_session(self) -> None:
        self.session.headers.update(
            {
                "Accept": "application/json, text/html;q=0.8",
                "User-Agent": "ALQuimista-Studio/0.9 (+desktop-confluence-exporter)",
            }
        )
        if self.options.proxy_mode == "direct":
            self.session.trust_env = False
        elif self.options.proxy_mode == "custom" and self.options.proxy_url:
            self.session.proxies.update(
                {"http": self.options.proxy_url, "https": self.options.proxy_url}
            )
        mode = self.source.auth_mode
        if mode == AuthMode.PUBLIC:
            return
        if urlparse(self.source.base_url).scheme != "https":
            raise AuthenticationError("A autenticação exige uma URL HTTPS.")
        if mode == AuthMode.BROWSER:
            legacy = Path(self.source.state_file) if self.source.state_file else None
            state = load_session(self.source.id, legacy_path=legacy)
            for cookie in state.get("cookies", []):
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain"),
                    path=cookie.get("path", "/"),
                )
            return
        if not self.secret:
            raise AuthenticationError(
                f"Informe a credencial temporária de “{self.source.name}”."
            )
        if mode == AuthMode.BASIC:
            self.session.auth = (self.source.username, self.secret)
        elif mode == AuthMode.BEARER:
            self.session.headers["Authorization"] = f"Bearer {self.secret}"

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> "ConfluenceClient":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _retry_delay(self, response: requests.Response | None, attempt: int) -> float:
        if response is not None:
            header = response.headers.get("Retry-After", "").strip()
            if header:
                if header.isdigit():
                    return min(float(header), 120.0)
                try:
                    parsed = parsedate_to_datetime(header)
                    return max(0.0, min(parsed.timestamp() - time.time(), 120.0))
                except (TypeError, ValueError):
                    pass
        return min(30.0, (2 ** (attempt - 1)) + self._random())

    def _request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        url = self._request_url(path)
        query = "" if not params else f" params={params!r}"
        self.log(f"[Confluence] GET {url}{query}")
        last_error: Exception | None = None
        for attempt in range(1, self.options.retry_count + 1):
            self.token.check()
            self.rate_limiter.wait()
            response: requests.Response | None = None
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=(
                        self.options.connect_timeout_seconds,
                        self.options.timeout_seconds,
                    ),
                )
                self.log(
                    f"[Confluence] resposta HTTP {response.status_code} "
                    f"({attempt}/{self.options.retry_count}) em {url}"
                )
                if response.status_code == 401:
                    raise AuthenticationError("Autenticação recusada ou sessão expirada (HTTP 401).")
                if response.status_code == 403:
                    raise PermissionDeniedError("A conta não possui permissão para este conteúdo (HTTP 403).")
                if response.status_code == 404:
                    raise ResourceNotFoundError("O espaço ou a página não foi encontrado (HTTP 404).")
                transient = response.status_code == 429 or response.status_code in {
                    500,
                    502,
                    503,
                    504,
                }
                if transient:
                    if attempt == self.options.retry_count:
                        if response.status_code == 429:
                            raise ApiRateLimitError(
                                f"O Confluence limitou as requisições (HTTP 429) em {url} "
                                f"após {attempt} tentativa(s)."
                            )
                        raise ApiConnectionError(
                            f"O Confluence permaneceu indisponível (HTTP {response.status_code}) "
                            f"em {url} após {attempt} tentativa(s)."
                        )
                    delay = self._retry_delay(response, attempt)
                    self.log(
                        f"Tentativa {attempt} falhou com HTTP {response.status_code} em {url}; "
                        f"nova tentativa em {delay:.1f}s."
                    )
                    self.token.wait(delay)
                    continue
                response.raise_for_status()
                if not expect_json:
                    return response.text
                try:
                    return response.json()
                except ValueError as exc:
                    raise InvalidResponseError(
                        "O Confluence retornou uma resposta JSON inválida."
                    ) from exc
            except (
                AuthenticationError,
                PermissionDeniedError,
                ResourceNotFoundError,
                InvalidResponseError,
                ApiRateLimitError,
            ):
                raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == self.options.retry_count:
                    break
                delay = self._retry_delay(response, attempt)
                self.log(
                    f"Falha de rede na tentativa {attempt}; nova tentativa em {delay:.1f}s."
                )
                self.token.wait(delay)
            except requests.RequestException as exc:
                raise ApiConnectionError(
                    f"Falha HTTP em {url}: {exc}"
                ) from exc
        raise ApiConnectionError(
            f"Não foi possível conectar ao Confluence em {url} após "
            f"{self.options.retry_count} tentativa(s): {last_error}"
        )

    def test_connection(self) -> dict[str, Any]:
        data = self._request("/rest/api/space", params={"limit": 1})
        return {"spaces_visible": data.get("size", len(data.get("results", [])))}

    def list_spaces(self, maximum: int = 1000) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        start = 0
        while len(items) < maximum:
            data = self._request(
                "/rest/api/space",
                params={
                    "limit": min(100, maximum - len(items)),
                    "start": start,
                    "expand": "icon",
                },
            )
            results = data.get("results", [])
            items.extend(
                {
                    "key": str(item.get("key", "")),
                    "name": str(item.get("name", item.get("key", ""))),
                    "type": str(item.get("type", "")),
                    # Mantém os dados opcionais para uma futura imagem em cache
                    # sem fazer uma chamada adicional por espaço.
                    "icon": item.get("icon"),
                    "links": item.get("_links") or {},
                }
                for item in results
            )
            if not results or not data.get("_links", {}).get("next"):
                break
            start += len(results)
        return items

    def list_pages(self, maximum: int = 5000) -> list[dict[str, Any]]:
        if not self.source.space_key:
            raise ResourceNotFoundError("Informe a chave do espaço.")
        items: list[dict[str, Any]] = []
        start = 0
        escaped = self.source.space_key.replace('"', '\\"')
        while len(items) < maximum:
            data = self._request(
                "/rest/api/content/search",
                params={
                    "cql": f'space="{escaped}" AND type=page',
                    "limit": min(100, maximum - len(items)),
                    "start": start,
                    "expand": "ancestors,version,space",
                },
            )
            results: list[dict[str, Any]] = []
            for page in data.get("results", []):
                enriched = self._enrich_page_restrictions(page)
                if isinstance(enriched, dict):
                    results.append(enriched)
            items.extend(results)
            if not results or not data.get("_links", {}).get("next"):
                break
            start += len(results)
        return _deduplicate(items)

    def _list_content_page(
        self,
        path: str,
        *,
        params: dict[str, Any],
        cursor: str | None,
        limit: int,
    ) -> dict[str, Any]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        try:
            start = int(cursor or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("cursor do Confluence deve ser um offset inteiro") from exc
        if start < 0:
            raise ValueError("cursor do Confluence não pode ser negativo")
        request_params = dict(params)
        request_params.update({"limit": limit, "start": start})
        data = self._request(path, params=request_params)
        results = data.get("results", [])
        if not isinstance(results, list):
            raise InvalidResponseError("A resposta de conteúdo do Confluence não possui results válido.")
        results = [self._enrich_page_restrictions(page) for page in results]
        has_next = bool((data.get("_links") or {}).get("next"))
        return {
            "results": results,
            "cursor": cursor,
            "next_cursor": str(start + len(results)) if has_next and results else None,
            "etag": None,
        }

    def _enrich_page_restrictions(self, page: object) -> object:
        """Load read restrictions when a content listing omits their details."""
        if (
            self.source.auth_mode == AuthMode.PUBLIC
            or not isinstance(page, dict)
            or self._has_restriction_details(page)
        ):
            return page

        expandable = page.get("_expandable") or {}
        restriction_url = (
            expandable.get("restrictions")
            if isinstance(expandable, dict)
            else None
        )
        page_id = page.get("id")
        if not page_id:
            return page
        if not isinstance(restriction_url, str) or not restriction_url.strip():
            if self.source.auth_mode == AuthMode.PUBLIC:
                return page
            restriction_url = f"/rest/api/content/{page_id}/restriction"

        endpoints = [restriction_url]
        if restriction_url.rstrip("/").endswith("/restriction"):
            endpoints.insert(0, restriction_url.rstrip("/") + "/byOperation/read")

        for endpoint in dict.fromkeys(endpoints):
            try:
                payload = self._request(
                    endpoint,
                    params={"expand": "restrictions.user,restrictions.group"},
                )
            except (ApiConnectionError, PermissionDeniedError, ResourceNotFoundError):
                continue
            restriction_data = self._read_restriction_payload(payload)
            if restriction_data is not None:
                enriched = dict(page)
                enriched["restrictions"] = {"read": restriction_data}
                return enriched
        return page

    @staticmethod
    def _has_restriction_details(page: dict[str, Any]) -> bool:
        for payload in (
            page.get("restrictions"),
            (page.get("metadata") or {}).get("restrictions"),
        ):
            if not isinstance(payload, dict):
                continue
            if isinstance(payload.get("read"), dict) or isinstance(payload.get("view"), dict):
                return True
        return False

    @staticmethod
    def _read_restriction_payload(payload: object) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        results = payload.get("results")
        if not isinstance(results, list):
            return payload
        operation_results = [
            item
            for item in results
            if isinstance(item, dict)
            and str(item.get("operation") or "").casefold() in {"read", "view"}
        ]
        if operation_results:
            return {**payload, "results": operation_results}
        if not results or all(
            not isinstance(item, dict) or "operation" not in item for item in results
        ):
            return payload
        return None

    def list_root_pages(
        self, *, cursor: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        """Return the first hierarchy below the space homepage.

        The public Confluence instance used by the application rejects the
        CQL ``ancestor is empty`` clause. Resolve the homepage first and use
        its direct-child endpoint instead. ``list_pages()`` remains the
        legacy full-space inventory used by the extraction path.
        """
        if not self.source.space_key:
            raise ResourceNotFoundError("Informe a chave do espaço.")
        space_key = self.source.space_key
        space = self._request(
            f"/rest/api/space/{space_key}",
            params={"expand": "homepage"},
        )
        homepage = space.get("homepage") or {}
        homepage_id = homepage.get("id")
        if not homepage_id:
            raise ResourceNotFoundError(
                f"O espaço '{space_key}' não possui uma homepage acessível."
            )
        return self._list_content_page(
            f"/rest/api/content/{homepage_id}/child/page",
            params={
                "expand": "ancestors,version,space,restrictions.read.restrictions",
            },
            cursor=cursor,
            limit=limit,
        )

    def list_child_pages(
        self,
        parent_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Return only direct page children of ``parent_id``."""
        if not str(parent_id).strip():
            raise ValueError("parent_id é obrigatório")
        return self._list_content_page(
            f"/rest/api/content/{parent_id}/child/page",
            params={
                "expand": "ancestors,version,space,restrictions.read.restrictions",
            },
            cursor=cursor,
            limit=limit,
        )

    def search_pages(
        self,
        query: str,
        *,
        container_id: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Search page metadata remotely using a bounded, title-only CQL query."""
        normalized = " ".join(query.split())
        if not normalized:
            raise ValueError("query não pode ser vazia")
        space_key = container_id or self.source.space_key
        if not space_key:
            raise ResourceNotFoundError("Informe o container_id para buscar no Confluence.")
        escaped_space = str(space_key).replace('"', '\\"')
        escaped_query = normalized.replace('"', '\\"')
        return self._list_content_page(
            "/rest/api/content/search",
            params={
                "cql": (
                    f'space="{escaped_space}" AND type=page '
                    f'title ~ "{escaped_query}" ORDER BY title'
                ),
                "expand": "ancestors,version,space",
            },
            cursor=cursor,
            limit=limit,
        )

    def resolve_root(self) -> dict[str, Any]:
        if self.source.root_mode == "space":
            if not self.source.space_key.strip():
                raise ResourceNotFoundError("Informe a chave do espaço.")
            data = self._request(
                f"/rest/api/space/{self.source.space_key}",
                params={"expand": "homepage"},
            )
            homepage = data.get("homepage") or {}
            if homepage.get("id"):
                return self.fetch_page(str(homepage["id"]), include_body=False)
            pages = self.list_pages()
            if not pages:
                raise ResourceNotFoundError("O espaço não possui páginas acessíveis.")
            return pages[0]
        if self.source.root_mode == "id":
            if not self.source.root_value.strip():
                raise ResourceNotFoundError("Informe o pageId da página raiz.")
            return self.fetch_page(self.source.root_value.strip(), include_body=False)
        title = self.source.root_value.strip()
        if not title:
            raise ResourceNotFoundError("Informe o título da página raiz.")
        data = self._request(
            "/rest/api/content",
            params={
                "spaceKey": self.source.space_key,
                "title": title,
                "type": "page",
                "expand": "ancestors,version,space,restrictions.read.restrictions",
            },
        )
        results = data.get("results", [])
        exact = next((item for item in results if str(item.get("title")) == title), None)
        if not exact:
            raise ResourceNotFoundError(
                f"A página raiz “{title}” não foi encontrada no espaço."
            )
        return exact

    def fetch_page(
        self, page_id: str, *, include_body: bool, include_labels: bool = False
    ) -> dict[str, Any]:
        expand = ["ancestors", "version", "space"]
        if include_body:
            expand.append("body.storage")
        if include_labels:
            expand.append("metadata.labels")
        return self._request(
            f"/rest/api/content/{page_id}", params={"expand": ",".join(expand)}
        )

    def list_descendant_pages(
        self, root_id: str, maximum: int = 5000
    ) -> list[dict[str, Any]]:
        """List every descendant of a root page in the provider response order."""
        if not str(root_id).strip():
            raise ValueError("root_id é obrigatório")
        pages: list[dict[str, Any]] = []
        start = 0
        while len(pages) < maximum:
            data = self._request(
                "/rest/api/content/search",
                params={
                    "cql": f"ancestor={root_id} AND type=page",
                    "expand": "ancestors,version,space",
                    "limit": min(100, maximum - len(pages)),
                    "start": start,
                },
            )
            results = data.get("results", [])
            if not isinstance(results, list):
                raise InvalidResponseError(
                    "A resposta de descendentes do Confluence não possui results válido."
                )
            pages.extend(results)
            if not results or not data.get("_links", {}).get("next"):
                break
            start += len(results)
        return _deduplicate(pages)

    def fetch_tree(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        root = self.resolve_root()
        if self.source.root_mode == "space":
            pages = self.list_pages()
            if not any(str(page.get("id")) == str(root["id"]) for page in pages):
                pages.insert(0, root)
            self.log(f"{len(pages)} páginas descobertas em {self.source.name}.")
            return root, _deduplicate(pages)
        root = self.fetch_page(str(root["id"]), include_body=False)
        root_id = str(root["id"])
        pages = [root]
        pages.extend(self.list_descendant_pages(root_id))
        self.log(f"{len(pages)} páginas descobertas em {self.source.name}.")
        return root, _deduplicate(pages)

    def fetch_html_fallback(self, page_id: str) -> str:
        return self._request(
            "/pages/viewpage.action", params={"pageId": page_id}, expect_json=False
        )

    @staticmethod
    def source_url(base_url: str, page: dict[str, Any]) -> str:
        webui = page.get("_links", {}).get("webui")
        if webui:
            return urljoin(base_url.rstrip("/") + "/", str(webui).lstrip("/"))
        return f"{base_url.rstrip('/')}/pages/viewpage.action?pageId={page['id']}"


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        identifier = str(item.get("id", ""))
        if identifier:
            unique[identifier] = item
    return list(unique.values())
