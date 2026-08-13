from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ..runtime import CancellationToken


class WorkerSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(object, str)
    progress = Signal(int, int, str)
    log = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(
        self,
        function: Callable[..., Any],
        *,
        token: CancellationToken | None = None,
    ) -> None:
        super().__init__()
        self.function = function
        self.token = token or CancellationToken()
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(
                self.token,
                self.signals.progress.emit,
                self.signals.log.emit,
            )
        except Exception as exc:
            self.signals.failed.emit(exc, traceback.format_exc())
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
