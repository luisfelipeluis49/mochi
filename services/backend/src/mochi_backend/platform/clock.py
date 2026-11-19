"""Time source behind a protocol so tests never read the wall clock."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current UTC time."""

    def now(self) -> datetime:
        """Return the current time as an aware UTC datetime."""
        ...


class SystemClock:
    """Real clock. Example: `SystemClock().now().tzinfo` is UTC."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


def iso_z(moment: datetime) -> str:
    """Format as ISO-8601 UTC with milliseconds and a Z suffix (AGENTS 6.1).

    Example: `iso_z(datetime(2026, 11, 19, 16, 0, 4, 700000, tzinfo=UTC))`
    returns `"2026-11-19T16:00:04.700Z"`.
    """
    utc = moment.astimezone(UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"
