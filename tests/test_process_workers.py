"""Deterministic contract tests for the Qt-independent spawn worker.

Spawn requires importable top-level task functions, so the fixtures below are
deliberately module-level rather than lambdas or nested functions.  The tests
use short bounded waits and no real network/API; this keeps subprocess
coverage repeatable on Windows while still exercising the real IPC boundary.
"""

from __future__ import annotations

import pickle
import time
from typing import Any

import pytest

from alquimista.ui.process_workers import ProcessWorker, TaskSerializationError, WorkerMessage


def return_payload(_context: Any, value: str) -> dict[str, str]:
    return {"value": value}


def report_progress(context: Any, count: int) -> int:
    for index in range(count):
        context.report_progress(index + 1, count, f"item-{index + 1}")
    return count


def cancellable_task(context: Any) -> str:
    for index in range(100):
        context.raise_if_cancelled()
        context.report_progress(index + 1, 100, f"item-{index + 1}")
        time.sleep(0.02)
    return "completed"


def failing_task(_context: Any) -> None:
    raise ValueError("expected worker failure")


def uncooperative_task(_context: Any) -> None:
    time.sleep(10)


def collect_until_finished(worker: ProcessWorker, timeout: float = 5.0) -> list[WorkerMessage]:
    deadline = time.monotonic() + timeout
    collected: list[WorkerMessage] = []
    while time.monotonic() < deadline:
        message = worker.receive(timeout=min(0.2, max(0.0, deadline - time.monotonic())))
        if message is not None:
            collected.append(message)
            if message.kind == "finished":
                return collected
    raise AssertionError("worker did not emit finished before timeout")


def test_worker_message_is_pickleable() -> None:
    message = WorkerMessage(kind="progress", done=2, total=4, item="page")

    restored = pickle.loads(pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL))

    assert restored == message


def test_non_serializable_task_is_rejected_before_start() -> None:
    worker = ProcessWorker(lambda _context: None)

    with pytest.raises(TaskSerializationError):
        worker.start()


def test_worker_reports_success_and_progress() -> None:
    worker = ProcessWorker(report_progress, args=(3,))
    worker.start()
    try:
        messages = collect_until_finished(worker)
    finally:
        worker.shutdown(timeout=2.0)

    progress = [message for message in messages if message.kind == "progress"]
    successes = [message for message in messages if message.kind == "success"]
    assert [(message.done, message.total, message.item) for message in progress] == [
        (1, 3, "item-1"),
        (2, 3, "item-2"),
        (3, 3, "item-3"),
    ]
    assert successes[0].result == 3
    assert messages[-1].kind == "finished"
    assert messages[-1].status == "success"


def test_worker_cancellation_is_cooperative() -> None:
    worker = ProcessWorker(cancellable_task)
    worker.start()
    try:
        first = worker.receive(timeout=5.0)
        assert first is not None and first.kind == "progress"
        worker.cancel()
        messages = collect_until_finished(worker)
    finally:
        worker.shutdown(timeout=2.0)

    kinds = [message.kind for message in messages]
    assert "cancelled" in kinds
    assert "success" not in kinds
    assert messages[-1].kind == "finished"
    assert messages[-1].status == "cancelled"


def test_worker_reports_serializable_error_and_finished() -> None:
    worker = ProcessWorker(failing_task)
    worker.start()
    try:
        messages = collect_until_finished(worker)
    finally:
        worker.shutdown(timeout=2.0)

    errors = [message for message in messages if message.kind == "error"]
    assert len(errors) == 1
    assert errors[0].error_type == "builtins.ValueError"
    assert errors[0].error_message == "expected worker failure"
    assert errors[0].error_traceback is not None
    assert "failing_task" in errors[0].error_traceback
    assert messages[-1].kind == "finished"
    assert messages[-1].status == "error"


def test_shutdown_terminates_uncooperative_task_after_timeout() -> None:
    worker = ProcessWorker(uncooperative_task)
    worker.start()

    started = time.monotonic()
    worker.shutdown(timeout=0.1)

    assert time.monotonic() - started < 5.0
    assert not worker.is_alive
