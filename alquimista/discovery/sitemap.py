from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import requests

from .models import DiscoveredResource

if TYPE_CHECKING:
    from ..models import ExtractionOptions
    from ..runtime import CancellationToken


def probe_sitemap(
    origin: str,
    session: requests.Session,
    options: ExtractionOptions,
    token: CancellationToken,
    max_pages: int = 100,
) -> tuple[str | None, list[DiscoveredResource]]:
    sitemap_url: str | None = None
    discovered: list[DiscoveredResource] = []

    for candidate in (f"{origin}/sitemap.xml", f"{origin}/sitemap_index.xml"):
        try:
            token.check()
            res = session.get(
                candidate,
                timeout=(options.connect_timeout_seconds, options.timeout_seconds),
            )
            if res.status_code == 200 and ("<urlset" in res.text or "<sitemapindex" in res.text):
                sitemap_url = candidate
                try:
                    root = ET.fromstring(res.content)
                    for elem in root.iter():
                        if "}" in elem.tag:
                            elem.tag = elem.tag.split("}", 1)[1]
                    for url_elem in root.findall(".//url/loc"):
                        if url_elem.text and len(discovered) < max_pages:
                            loc_url = url_elem.text.strip()
                            discovered.append(
                                DiscoveredResource(
                                    url=loc_url,
                                    title=loc_url,
                                    resource_type="page",
                                )
                            )
                except Exception:
                    pass
                break
        except Exception:
            pass

    return sitemap_url, discovered


__all__ = ["probe_sitemap"]
