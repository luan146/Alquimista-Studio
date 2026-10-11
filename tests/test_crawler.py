from __future__ import annotations

from typing import Any

from alquimista.discovery.crawler import WebCrawler

PAGES = {
    "https://docs.test/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /privado\n"),
    "https://docs.test/": (
        200,
        "text/html",
        '<title>Início</title><a href="/guia">g</a><a href="/privado/x">p</a><a href="/sai">s</a>',
    ),
    "https://docs.test/guia": (200, "text/html", "<title>Guia</title>"),
    "https://docs.test/privado/x": (200, "text/html", "<title>Privado</title>"),
    "https://docs.test/sai": (200, "text/html", "<title>Fora</title>"),
}


class _Response:
    def __init__(self, url: str) -> None:
        self.status_code, content_type, self.text = PAGES.get(url, (404, "text/html", ""))
        self.headers = {"Content-Type": content_type}
        # Simulates a redirect that leaves the allowed domain.
        self.url = "https://outro.test/destino" if url.endswith("/sai") else url


class _Session:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def get(self, url: str, **_kwargs: Any) -> _Response:
        self.requested.append(url)
        return _Response(url)

    def close(self) -> None:
        pass


def _crawl(respect_robots: bool) -> tuple[set[str], list[str]]:
    crawler = WebCrawler("https://docs.test", respect_robots=respect_robots)
    crawler.session = _Session()  # type: ignore[assignment]
    titles = {resource.title for resource in crawler.crawl()}
    return titles, crawler.session.requested  # type: ignore[attr-defined]


def test_crawler_respects_robots_and_ignores_off_domain_redirects() -> None:
    titles, requested = _crawl(respect_robots=True)
    assert titles == {"Início", "Guia"}
    assert "https://docs.test/privado/x" not in requested


def test_crawler_can_opt_out_of_robots() -> None:
    titles, _ = _crawl(respect_robots=False)
    assert "Privado" in titles
    assert "Fora" not in titles
