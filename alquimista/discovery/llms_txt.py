from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import requests

from .models import DiscoveredResource

if TYPE_CHECKING:
    from ..models import ExtractionOptions
    from ..runtime import CancellationToken


def probe_llms_txt(
    origin: str,
    session: requests.Session,
    options: ExtractionOptions,
    token: CancellationToken,
) -> tuple[str | None, list[DiscoveredResource]]:
    parsed = urlsplit(origin)
    discovered: list[DiscoveredResource] = []
    llms_txt_url: str | None = None

    for candidate in (f"{origin}/llms-full.txt", f"{origin}/llms.txt"):
        try:
            token.check()
            res = session.get(
                candidate,
                timeout=(options.connect_timeout_seconds, options.timeout_seconds),
            )
            if res.status_code == 200 and len(res.text.strip()) > 20:
                llms_txt_url = candidate
                discovered.append(
                    DiscoveredResource(
                        url=candidate,
                        title=f"llms.txt ({parsed.netloc})",
                        resource_type="llms_txt",
                    )
                )
                break
        except Exception:
            pass

    return llms_txt_url, discovered


__all__ = ["probe_llms_txt"]
