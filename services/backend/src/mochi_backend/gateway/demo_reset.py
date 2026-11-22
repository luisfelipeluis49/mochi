"""`POST /api/demo/reset`: clear saved words and the learning history; keep capturing as it is."""

from mochi_backend.gateway.core import GatewayCore
from mochi_backend.team.ledger import TeamLedger
from mochi_contracts import EventType


class DemoReset:
    """Resets intelligence, history and the live hint, then republishes the session state."""

    def __init__(self, core: GatewayCore, ledger: TeamLedger) -> None:
        self._ledger = ledger
        self._store = core.store
        self._hub = core.hub
        self._live_hint = core.live_hint
        self._intelligence = core.intelligence
        self._silence = core.silence
        self._commit = core.commit
        self._journal = core.journal

    async def run(self) -> None:
        """Back to the start: no words, no hint, no learning history; a fresh session state."""
        self._store.invalidate()  # a turn still deciding must not publish into the fresh state
        async with self._commit:  # a turn that is mid-publish finishes first
            await self._live_hint.clear()
            self._intelligence.reset()
            self._store.clear_history()
            self._journal.forget()
            self._ledger.clear_history()
            self._hub.reset()
            self._silence.finished_speaking()
            await self._hub.publish(EventType.SESSION_STATE_CHANGED, self._store.session_state())
