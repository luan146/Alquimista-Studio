from __future__ import annotations

import random
import time
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import requests

from ..errors import (
    ApiConnectionError,
    ApiRateLimitError,
    AuthenticationError,
    InvalidResponseError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from ..models import ExtractionOptions
from ..runtime import CancellationToken, LogCallback, RateLimiter


class ApiHttpClient:
    """Small HTTP layer shared by official API connectors.

    Authorization is kept in the session and is never included in logs or
    exception messages.
    """

    def __init__(
        self,
        base_url: str,
        options: ExtractionOptions,
        *,
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        headers: dict[str, str] | None = None,
        session: requests.Session | None = None,
        sleep: Any = time.sleep,
        random_value: Any = random.random,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("A API do conector deve usar uma URL HTTPS válida.")
        self.base_url = base_url.rstrip("/")
        self.options = options
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self._owns_session = session is None
        self.session = session or requests.Session()
        self._sleep = sleep
        self._random = random_value
        self.last_response_headers: dict[str, str] = {}
        self.rate_limiter = RateLimiter(options.max_requests_per_second, self.token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "ALQuimista-Studio/5.0 (+official-knowledge-connector)",
                **(headers or {}),
            }
        )
        if options.proxy_mode == "direct":
            self.session.trust_env = False
        elif options.proxy_mode == "custom" and options.proxy_url:
            self.session.proxies.update(
                {"http": options.proxy_url, "https": options.proxy_url}
            )

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        return self._request_json("GET", path, params=params)

    def post_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        return self._request_json("POST", path, params=params, json_body=json_body)

    def download(self, path: str, *, params: dict[str, Any] | None = None) -> bytes:
        """Download a binary resource with bounded retries and cancellation."""
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(1, self.options.retry_count + 1):
            self.token.check()
            self.rate_limiter.wait()
            response: requests.Response | None = None
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=(self.options.connect_timeout_seconds, self.options.timeout_seconds),
                )
                if response.status_code == 401:
                    raise AuthenticationError("A API recusou o token (HTTP 401).")
                if response.status_code == 403:
                    raise PermissionDeniedError("A conta não possui permissão para este conteúdo (HTTP 403).")
                if response.status_code == 404:
                    raise ResourceNotFoundError("O recurso solicitado não foi encontrado (HTTP 404).")
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt == self.options.retry_count:
                        if response.status_code == 429:
                            raise ApiRateLimitError("A API limitou as requisições após o limite de tentativas.")
                        raise ApiConnectionError(f"A API permaneceu indisponível (HTTP {response.status_code}).")
                    self.token.wait(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                return response.content
            except (AuthenticationError, PermissionDeniedError, ResourceNotFoundError, ApiRateLimitError):
                raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == self.options.retry_count:
                    break
                self.token.wait(self._retry_delay(response, attempt))
            except requests.RequestException as exc:
                raise ApiConnectionError(f"Falha HTTP na API: {exc}") from exc
        raise ApiConnectionError(
            f"Não foi possível baixar o recurso após {self.options.retry_count} tentativas: {last_error}"
        )

    def _download_compat(self, path: str, *, params: dict[str, Any] | None = None) -> bytes:
        """Compatibility alias for older connector code."""
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(1, self.options.retry_count + 1):
            self.token.check()
            self.rate_limiter.wait()
            response: requests.Response | None = None
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=(self.options.connect_timeout_seconds, self.options.timeout_seconds),
                )
                if response.status_code == 401:
                    raise AuthenticationError("A API recusou o token (HTTP 401).")
                if response.status_code == 403:
                    raise PermissionDeniedError("A conta não possui permissão para este conteúdo (HTTP 403).")
                if response.status_code == 404:
                    raise ResourceNotFoundError("O recurso solicitado não foi encontrado (HTTP 404).")
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt == self.options.retry_count:
                        if response.status_code == 429:
                            raise ApiRateLimitError("A API limitou as requisições após o limite de tentativas.")
                        raise ApiConnectionError(f"A API permaneceu indisponível (HTTP {response.status_code}).")
                    self.token.wait(self._retry_delay(response, attempt))
                    continue
                response.raise_for_status()
                return response.content
            except (AuthenticationError, PermissionDeniedError, ResourceNotFoundError, ApiRateLimitError):
                raise
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == self.options.retry_count:
                    break
                self.token.wait(self._retry_delay(response, attempt))
            except requests.RequestException as exc:
                raise ApiConnectionError(f"Falha HTTP na API: {exc}") from exc
        raise ApiConnectionError(
            f"Não foi possível baixar o recurso após {self.options.retry_count} tentativas: {last_error}"
        )

    def _retry_delay(self, response: requests.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "").strip()
            if retry_after.isdigit():
                return min(float(retry_after), 120.0)
            if retry_after:
                try:
                    parsed = parsedate_to_datetime(retry_after)
                    return max(0.0, min(parsed.timestamp() - time.time(), 120.0))
                except (TypeError, ValueError):
                    pass
            reset = response.headers.get("X-RateLimit-Reset", "").strip()
            if reset.isdigit():
                return max(0.0, min(float(reset) - time.time(), 120.0))
        return min(30.0, (2 ** (attempt - 1)) + self._random())

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> Any:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        last_error: Exception | None = None
        for attempt in range(1, self.options.retry_count + 1):
            self.token.check()
            self.rate_limiter.wait()
            response: requests.Response | None = None
            try:
                request = getattr(self.session, method.casefold())
                response = request(
                    url,
                    params=params,
                    json=json_body,
                    timeout=(
                        self.options.connect_timeout_seconds,
                        self.options.timeout_seconds,
                    ),
                )
                if response.status_code == 401:
                    raise AuthenticationError("A API recusou o token (HTTP 401).")
                if response.status_code == 403:
                    raise PermissionDeniedError("A conta não possui permissão para este conteúdo (HTTP 403).")
                if response.status_code == 404:
                    raise ResourceNotFoundError("O recurso solicitado não foi encontrado (HTTP 404).")
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt == self.options.retry_count:
                        if response.status_code == 429:
                            raise ApiRateLimitError("A API limitou as requisições após o limite de tentativas.")
                        raise ApiConnectionError(f"A API permaneceu indisponível (HTTP {response.status_code}).")
                    delay = self._retry_delay(response, attempt)
                    self.log(f"API temporariamente indisponível (HTTP {response.status_code}); nova tentativa em {delay:.1f}s.")
                    self.token.wait(delay)
                    continue
                response.raise_for_status()
                self.last_response_headers = {
                    str(key).casefold(): str(value)
                    for key, value in response.headers.items()
                }
                try:
                    return response.json()
                except ValueError as exc:
                    raise InvalidResponseError("A API retornou JSON inválido.") from exc
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
                self.log(f"Falha transitória de rede; nova tentativa em {delay:.1f}s.")
                self.token.wait(delay)
            except requests.RequestException as exc:
                raise ApiConnectionError(f"Falha HTTP na API: {exc}") from exc
        raise ApiConnectionError(
            f"Não foi possível conectar à API após {self.options.retry_count} tentativas: {last_error}"
        )
