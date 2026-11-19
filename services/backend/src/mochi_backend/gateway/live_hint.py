"""The one hint on screen: publish it, schedule its expiry, replace it when a newer one arrives."""

from datetime import timedelta

from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.platform.clock import Clock, parse_iso_z
from mochi_backend.platform.scheduler import ScheduledCall, Scheduler
from mochi_contracts import EventType, Hint, HintCleared


class LiveHint:
    """Tracks the live hint. Example: `await live.show(hint)`; it clears itself at `expires_at`."""

    def __init__(self, hub: EventHub, clock: Clock, scheduler: Scheduler) -> None:
        self._hub = hub
        self._clock = clock
        self._scheduler = scheduler
        self._current: Hint | None = None
        self._expiry: ScheduledCall | None = None

    @property
    def current(self) -> Hint | None:
        """The hint on screen right now, if any."""
        return self._current

    async def show(self, hint: Hint) -> None:
        """Clear the previous hint at once, publish this one, schedule its `hint.cleared`."""
        await self.clear()
        self._current = hint
        await self._hub.publish(EventType.HINT_CREATED, hint)
        delay = (parse_iso_z(hint.expires_at) - self._clock.now()) / timedelta(seconds=1)
        self._expiry = self._scheduler.call_later(max(delay, 0.0), lambda: self._expire(hint))

    async def clear(self) -> None:
        """Publish `hint.cleared` for the live hint and cancel its expiry (no-op when none)."""
        hint, self._current = self._current, None
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        if hint is not None:
            await self._hub.publish(EventType.HINT_CLEARED, HintCleared(hint_id=hint.hint_id))

    async def _expire(self, hint: Hint) -> None:
        if self._current is not None and self._current.hint_id == hint.hint_id:
            self._expiry = None
            await self.clear()
