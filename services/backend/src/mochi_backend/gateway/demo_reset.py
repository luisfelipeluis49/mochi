"""`POST /api/demo/reset`: clear saved words and any game; keep capturing as it is."""

from mochi_backend.gateway.core import GatewayCore
from mochi_contracts import EventType


class DemoReset:
    """Resets intelligence, history, the live hint and the game, then republishes states."""

    def __init__(self, core: GatewayCore) -> None:
        self._store = core.store
        self._hub = core.hub
        self._live_hint = core.live_hint
        self._intelligence = core.intelligence
        self._silence = core.silence
        self._commit = core.commit

    async def run(self) -> None:
        """Back to the start: no words, no game, no hint; fresh session and IDLE activity."""
        self._store.invalidate()  # a turn still deciding must not publish into the fresh state
        async with self._commit:  # a turn or round change that is mid-publish finishes first
            await self._live_hint.clear()
            self._intelligence.reset()
            self._store.clear_history()
            self._hub.reset()
            self._silence.finished_speaking()
            await self._hub.publish(EventType.SESSION_STATE_CHANGED, self._store.session_state())
            await self._hub.publish(EventType.ACTIVITY_STATE_CHANGED, self._store.activity)
