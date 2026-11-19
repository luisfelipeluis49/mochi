"""A scheduler that never sleeps: callbacks run when a test calls `run_due()`."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from mochi_backend.platform.scheduler import Callback
from tests.fakes.fake_clock import FakeClock


@dataclass
class FakeScheduledCall:
    """Cancel handle that also remembers its due time."""

    due: datetime
    callback: Callback
    cancelled: bool = field(default=False)

    def cancel(self) -> None:
        """Mark as cancelled; `run_due` skips it."""
        self.cancelled = True


class FakeScheduler:
    """Implements `platform.scheduler.Scheduler` against a `FakeClock`."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.calls: list[FakeScheduledCall] = []

    def call_later(self, delay_seconds: float, callback: Callback) -> FakeScheduledCall:
        """Record the callback to run `delay_seconds` after the fake now."""
        due = self._clock.now() + timedelta(seconds=delay_seconds)
        call = FakeScheduledCall(due=due, callback=callback)
        self.calls.append(call)
        return call

    async def run_due(self) -> int:
        """Run every uncancelled callback that is due; returns how many ran."""
        ran = 0
        for call in sorted(self.calls, key=lambda c: c.due):
            if call.cancelled or call.due > self._clock.now():
                continue
            call.cancelled = True
            await call.callback()
            ran += 1
        return ran
