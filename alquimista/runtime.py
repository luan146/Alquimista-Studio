from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .errors import ExtractionCancelledError


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self.cancelled:
            raise ExtractionCancelledError("Operação cancelada pelo usuário.")

    def wait(self, seconds: float) -> None:
        if seconds > 0 and self._event.wait(seconds):
            self.check()


ProgressCallback = Callable[[int, int, str], None]
LogCallback = Callable[[str], None]


class RateLimiter:
    def __init__(self, requests_per_second: float, token: CancellationToken) -> None:
        self.interval = 1.0 / max(0.1, requests_per_second)
        self.last_request = 0.0
        self.token = token
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            remaining = self.interval - (time.monotonic() - self.last_request)
            if remaining > 0:
                self.token.wait(remaining)
            self.last_request = time.monotonic()
