"""Delayed callbacks behind a protocol so tests never sleep."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

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
    """Real scheduler on the running event loop."""

    def call_later(self, delay_seconds: float, callback: Callback) -> ScheduledCall:
        """Run `callback` after `delay_seconds`. Example: expire a hint after 8 s."""
        return asyncio.get_running_loop().call_later(
            delay_seconds, lambda: asyncio.ensure_future(callback())
        )
