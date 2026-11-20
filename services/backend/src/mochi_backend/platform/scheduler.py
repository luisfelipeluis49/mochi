"""Delayed callbacks behind a protocol so tests never sleep."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from mochi_backend.platform.json_logging import EventLogger

Callback = Callable[[], Awaitable[None]]


class Scheduler(Protocol):
    """Runs a callback once after a delay."""

    def call_later(self, delay_seconds: float, callback: Callback) -> "ScheduledCall":
        """Schedule `callback` after `delay_seconds` and return a cancel handle."""
        ...


class ScheduledCall(Protocol):
    """Handle for a scheduled callback."""

    def cancel(self) -> None:
        """Cancel the callback if it has not run yet."""
        ...


class AsyncioScheduler:
    """Real scheduler on the running event loop.

    Keeps a reference to every task it starts (the loop only holds weak references) and logs
    a callback that raises instead of dropping the error.
    """

    def __init__(self, logger: EventLogger) -> None:
        self._logger = logger
        self._running: set[asyncio.Task[None]] = set()

    def call_later(self, delay_seconds: float, callback: Callback) -> ScheduledCall:
        """Run `callback` after `delay_seconds`. Example: expire a hint after 8 s."""
        return asyncio.get_running_loop().call_later(delay_seconds, lambda: self._launch(callback))

    def _launch(self, callback: Callback) -> None:
        task = asyncio.ensure_future(callback())
        self._running.add(task)
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self._running.discard(task)
        if task.cancelled() or task.exception() is None:
            return
        self._logger.log("scheduled_call_failed", {"error": repr(task.exception())})
