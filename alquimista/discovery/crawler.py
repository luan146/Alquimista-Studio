from __future__ import annotations

from collections import deque
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from ..models import ExtractionOptions
from ..runtime import CancellationToken, RateLimiter
from .models import DiscoveredResource
from .normalization import DEFAULT_USER_AGENT, is_url_in_scope, normalize_web_url


class WebCrawler:
    """Safe bounded crawler exploring internal documentation pages within scope."""

    def __init__(
        self,
        base_url: str,
        options: ExtractionOptions | None = None,
        *,
        token: CancellationToken | None = None,
        max_depth: int = 3,
        max_pages: int = 200,
        allowed_domains: set[str] | None = None,
        respect_robots: bool = True,
    ) -> None:
        self.base_url = normalize_web_url(base_url)
        parsed = urlsplit(self.base_url)
        self.hostname = parsed.hostname or ""
        self.allowed_domains = allowed_domains or {self.hostname}
        self.options = options or ExtractionOptions()
        self.token = token or CancellationToken()
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.respect_robots = respect_robots
        self.rate_limiter = RateLimiter(self.options.max_requests_per_second, self.token)
        self.session = requests.Session()
        self.session.trust_env = False
        adapter = requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16, max_retries=0)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def close(self) -> None:
        self.session.close()

    def _is_url_in_scope(self, url: str) -> bool:
        return is_url_in_scope(url, self.allowed_domains)

    def crawl(self) -> list[DiscoveredResource]:
        visited: set[str] = set()
        queue: deque[tuple[str, int, str | None]] = deque([(self.base_url, 0, None)])
        results: list[DiscoveredResource] = []

        while queue and len(results) < self.max_pages:
            self.token.check()
            current_url, depth, parent_url = queue.popleft()

            clean_url = normalize_web_url(current_url)
            if clean_url in visited:
                continue
            visited.add(clean_url)

            if depth > self.max_depth:
                continue

            try:
                self.rate_limiter.wait()
                response = self.session.get(
                    clean_url,
                    timeout=(self.options.connect_timeout_seconds, self.options.timeout_seconds),
                    allow_redirects=True,
                )
                if response.status_code != 200:
                    continue

                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    continue

                html_text = response.text
                soup = BeautifulSoup(html_text, "html.parser")

                title = ""
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    title = str(og_title["content"]).strip()
                elif soup.title and soup.title.string:
                    title = str(soup.title.string).strip()
                elif soup.find("h1"):
                    title = soup.find("h1").get_text(" ", strip=True)
                title = title or clean_url

                canonical_tag = soup.find("link", rel="canonical")
                canonical_url = clean_url
                if canonical_tag and canonical_tag.get("href"):
                    cand = urljoin(clean_url, str(canonical_tag["href"]).strip())
                    if self._is_url_in_scope(cand):
                        canonical_url = normalize_web_url(cand)

                results.append(
                    DiscoveredResource(
                        url=canonical_url,
                        title=title,
                        resource_type="page",
                        parent_url=parent_url,
                        depth=depth,
                        metadata={
                            "etag": response.headers.get("ETag"),
                            "last_modified": response.headers.get("Last-Modified"),
                        },
                    )
                )

                if depth < self.max_depth:
                    for link in soup.find_all("a", href=True):
                        href = link["href"].strip()
                        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
                            continue
                        abs_url = urljoin(clean_url, href)
                        split_link = urlsplit(abs_url)
                        target = urlunsplit(
                            (split_link.scheme, split_link.netloc, split_link.path, "", "")
                        )
                        if self._is_url_in_scope(target) and target not in visited:
                            queue.append((target, depth + 1, canonical_url))

            except Exception:
                continue

        return results


__all__ = ["WebCrawler"]
