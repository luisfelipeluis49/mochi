"""A clock tests control. Example: `clock.advance(1.0)` moves time one second."""

from datetime import UTC, datetime, timedelta

START = datetime(2026, 11, 19, 16, 0, 0, tzinfo=UTC)


class FakeClock:
    """Implements `platform.clock.Clock` with a manually advanced time."""

    def __init__(self, start: datetime = START) -> None:
        self._now = start

    def now(self) -> datetime:
        """The current fake time."""
        return self._now

    def advance(self, seconds: float) -> None:
        """Move time forward."""
        self._now += timedelta(seconds=seconds)

    def set(self, moment: datetime) -> None:
        """Jump to an absolute time."""
        self._now = moment
