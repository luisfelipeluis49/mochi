"""`POST /api/demo/reset`: clear saved words and any game; keep capturing as it is."""

from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.session_store import SessionStore
from mochi_contracts import EventType


class DemoReset:
    """Resets intelligence, history, the live hint and the game, then republishes states."""

    def __init__(
        self,
        store: SessionStore,
        hub: EventHub,
        live_hint: LiveHint,
        intelligence: IntelligencePort,
    ) -> None:
        self._store = store
        self._hub = hub
        self._live_hint = live_hint
        self._intelligence = intelligence

    async def run(self) -> None:
        """Back to the start: no words, no game, no hint; fresh session and IDLE activity."""
        await self._live_hint.clear()
        self._intelligence.reset()
        self._store.clear_history()
        self._hub.reset()
        await self._hub.publish(EventType.SESSION_STATE_CHANGED, self._store.session_state())
        await self._hub.publish(EventType.ACTIVITY_STATE_CHANGED, self._store.activity)
