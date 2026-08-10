"""Small, Qt-independent process worker for future UI integration.

The task callable and its arguments must be importable/pickleable because the
worker always uses a ``spawn`` multiprocessing context.  The child process
only communicates through :class:`WorkerMessage` instances and never receives
Qt objects.
"""

from __future__ import annotations

import multiprocessing
import pickle
import queue
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Sequence

MessageKind = Literal["progress", "success", "error", "cancelled", "finished"]
Task = Callable[..., Any]


class TaskSerializationError(TypeError):
    """Raised when a task or its arguments cannot cross the spawn boundary."""


class TaskCancelled(Exception):
    """Raised by :class:`TaskContext` when cooperative cancellation is seen."""


@dataclass(frozen=True, slots=True)
class WorkerMessage:
    """Serializable message emitted by a worker process."""

    kind: MessageKind
    done: int | None = None
    total: int | None = None
    item: str | None = None
    result: Any = None
    error_type: str | None = None
    error_message: str | None = None
    error_traceback: str | None = None
    status: str | None = None


class TaskContext:
    """Child-side context for progress reporting and cooperative cancellation."""

    def __init__(self, cancel_event: Any, messages: Any) -> None:
        self._cancel_event = cancel_event
        self._messages = messages

    def cancelled(self) -> bool:
        """Return whether the parent requested cancellation."""

        return bool(self._cancel_event.is_set())

    def raise_if_cancelled(self) -> None:
        """Raise :class:`TaskCancelled` if cancellation was requested."""

        if self.cancelled():
            raise TaskCancelled("Worker cancellation requested")

    def report_progress(self, done: int, total: int, item: str = "") -> None:
        """Send a small, serializable progress message to the parent."""

        self._messages.put(
            WorkerMessage(
                kind="progress",
                done=int(done),
                total=int(total),
                item=str(item),
            )
        )


def _error_message(error: BaseException) -> WorkerMessage:
    """Convert an exception into bounded, serializable diagnostic fields."""

    error_type = f"{type(error).__module__}.{type(error).__qualname__}"
    error_text = str(error) or type(error).__name__
    stack = traceback.format_exc(limit=20)
    return WorkerMessage(
        kind="error",
        error_type=error_type[:512],
        error_message=error_text[:4096],
        error_traceback=stack[-16384:],
    )


def _worker_main(
    task: Task,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    cancel_event: Any,
    messages: Any,
) -> None:
    """Run a serialized task and always emit ``finished`` on normal cleanup."""

    context = TaskContext(cancel_event, messages)
    status = "error"
    try:
        context.raise_if_cancelled()
        result = task(context, *args, **kwargs)
        context.raise_if_cancelled()

        # Fail inside the child, before Queue's feeder thread can report an
        # opaque asynchronous pickling error to the parent.
        pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
        messages.put(WorkerMessage(kind="success", result=result))
        status = "success"
    except TaskCancelled:
        messages.put(WorkerMessage(kind="cancelled", status="cancelled"))
        status = "cancelled"
    except BaseException as error:
        messages.put(_error_message(error))
        status = "error"
    finally:
        messages.put(WorkerMessage(kind="finished", status=status))


class ProcessWorker:
    """Execute one serializable task in a dedicated ``spawn`` process.

    A worker is single-use.  Call :meth:`receive` until ``finished`` arrives,
    then call :meth:`close` to release IPC resources.  :meth:`shutdown` is a
    convenience for teardown: it requests cancellation, waits up to the
    supplied timeout, and force-terminates a task that does not cooperate.
    """

    def __init__(
        self,
        task: Task,
        args: Sequence[Any] = (),
        kwargs: Mapping[str, Any] | None = None,
        *,
        name: str | None = None,
    ) -> None:
        if not callable(task):
            raise TypeError("task must be callable")
        self._task = task
        self._args = tuple(args)
        self._kwargs = dict(kwargs or {})
        self._name = name or "AlquimistaProcessWorker"
        self._context = multiprocessing.get_context("spawn")
        self._process: Any = None
        self._cancel_event: Any = None
        self._messages: Any = None
        self._closed = False

    @property
    def is_alive(self) -> bool:
        """Whether the child process is currently running."""

        return bool(self._process is not None and self._process.is_alive())

    @property
    def exitcode(self) -> int | None:
        """Child exit code, or ``None`` before it exits/starts."""

        return None if self._process is None else self._process.exitcode

    def start(self) -> None:
        """Validate serialization and start the spawned child process."""

        if self._process is not None:
            raise RuntimeError("ProcessWorker instances are single-use")
        if self._closed:
            raise RuntimeError("ProcessWorker is closed")
        try:
            pickle.dumps(
                (self._task, self._args, self._kwargs),
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        except Exception as error:
            raise TaskSerializationError(
                "task, args, and kwargs must be serializable for spawn"
            ) from error

        self._messages = self._context.Queue()
        self._cancel_event = self._context.Event()
        self._process = self._context.Process(
            target=_worker_main,
            args=(self._task, self._args, self._kwargs, self._cancel_event, self._messages),
            name=self._name,
        )
        try:
            self._process.start()
        except Exception:
            self._process = None
            self._close_queue()
            raise

    def receive(self, timeout: float | None = None) -> WorkerMessage | None:
        """Read one message, returning ``None`` when the timeout expires."""

        if self._messages is None or self._closed:
            raise RuntimeError("ProcessWorker has not been started or is closed")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        try:
            return self._messages.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> list[WorkerMessage]:
        """Return currently available messages without waiting."""

        if self._messages is None or self._closed:
            raise RuntimeError("ProcessWorker has not been started or is closed")
        messages: list[WorkerMessage] = []
        while True:
            try:
                messages.append(self._messages.get_nowait())
            except queue.Empty:
                return messages

    def cancel(self) -> None:
        """Request cooperative cancellation; the task must check its context."""

        if self._cancel_event is not None:
            self._cancel_event.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for completion and return ``True`` if the child exited."""

        if self._process is None:
            raise RuntimeError("ProcessWorker has not been started")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must be non-negative or None")
        self._process.join(timeout)
        return not self._process.is_alive()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Cancel, wait, and force-terminate if the task ignores cancellation."""

        if timeout < 0:
            raise ValueError("timeout must be non-negative")
        if self._process is None:
            self.close()
            return
        if self.is_alive:
            self.cancel()
            if not self.wait(timeout):
                self._process.terminate()
                self._process.join(timeout)
                if self.is_alive:
                    kill = getattr(self._process, "kill", None)
                    if kill is not None:
                        kill()
                    self._process.join(timeout)
        self.close()

    def close(self) -> None:
        """Release the queue after the child has exited."""

        if self._process is not None and self.is_alive:
            raise RuntimeError("cannot close a running ProcessWorker")
        self._close_queue()
        self._closed = True

    def _close_queue(self) -> None:
        if self._messages is not None:
            self._messages.close()
            self._messages.join_thread()
            self._messages = None

    def __enter__(self) -> ProcessWorker:
        return self

    def __exit__(self, _exc_type: Any, _exc_value: Any, _traceback: Any) -> None:
        self.shutdown()


__all__ = [
    "ProcessWorker",
    "TaskCancelled",
    "TaskContext",
    "TaskSerializationError",
    "WorkerMessage",
]
