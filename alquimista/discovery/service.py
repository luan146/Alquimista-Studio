from __future__ import annotations

from urllib.parse import urlsplit

import requests

from ..models import ExtractionOptions
from ..runtime import CancellationToken
from ..source_detection import detect_source_url
from .crawler import WebCrawler
from .frameworks import detect_documentation_framework
from .llms_txt import probe_llms_txt
from .models import DiscoveredResource, DiscoveryResult, DiscoveryStrategy
from .normalization import DEFAULT_USER_AGENT
from .sitemap import probe_sitemap


class SourceDiscoveryService:
    """Universal discovery layer resolving optimal extraction strategies for any URL."""

    def __init__(
        self,
        options: ExtractionOptions | None = None,
        *,
        token: CancellationToken | None = None,
    ) -> None:
        self.options = options or ExtractionOptions()
        self.token = token or CancellationToken()
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def close(self) -> None:
        self.session.close()

    def discover(
        self,
        url: str,
        *,
        deep_crawl: bool = False,
        max_pages: int = 100,
    ) -> DiscoveryResult:
        detected = detect_source_url(url)
        parsed = urlsplit(detected.base_url or url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        # If detected as dedicated closed enterprise platform, return immediately
        if detected.source_type not in {"generic_web"}:
            return DiscoveryResult(
                strategy=DiscoveryStrategy.OFFICIAL_API,
                detected_source=detected,
                resources=[
                    DiscoveredResource(
                        url=url, title=detected.display_name, resource_type="api"
                    )
                ],
            )

        # For generic web / doc sites, test in order: llms.txt -> sitemap.xml -> crawler
        llms_txt_url, llms_resources = probe_llms_txt(
            origin, self.session, self.options, self.token
        )
        sitemap_url, sitemap_resources = probe_sitemap(
            origin, self.session, self.options, self.token, max_pages=max_pages
        )

        framework: str | None = None
        try:
            home_res = self.session.get(
                url,
                timeout=(
                    self.options.connect_timeout_seconds,
                    self.options.timeout_seconds,
                ),
            )
            if home_res.status_code == 200:
                framework = detect_documentation_framework(home_res.text)
        except Exception:
            pass

        strategy = DiscoveryStrategy.SINGLE_PAGE
        discovered_resources: list[DiscoveredResource] = []

        if llms_txt_url:
            strategy = DiscoveryStrategy.LLMS_TXT
            discovered_resources = llms_resources
        elif sitemap_url and sitemap_resources:
            strategy = DiscoveryStrategy.SITEMAP
            discovered_resources = sitemap_resources
        elif deep_crawl:
            crawler = WebCrawler(
                url, options=self.options, token=self.token, max_pages=max_pages
            )
            crawled = crawler.crawl()
            crawler.close()
            if len(crawled) > 1:
                strategy = DiscoveryStrategy.HTML_CRAWLER
                discovered_resources = crawled

        if not discovered_resources:
            discovered_resources = [
                DiscoveredResource(
                    url=url,
                    title=url,
                    resource_type="page",
                )
            ]

        return DiscoveryResult(
            strategy=strategy,
            detected_source=detected,
            resources=discovered_resources,
            llms_txt_url=llms_txt_url,
            sitemap_url=sitemap_url,
            framework=framework,
            meta={"origin": origin, "total_resources": len(discovered_resources)},
        )


__all__ = ["SourceDiscoveryService"]
