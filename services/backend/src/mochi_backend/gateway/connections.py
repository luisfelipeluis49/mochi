"""A client connects: register it, then send the current state as normal enveloped events."""

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import Connection, EventHub, Sender
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.roster import HOME_DEVICE_ID, USER_IDS
from mochi_backend.gateway.session_store import SessionStore
from mochi_contracts import EventPayload, EventType, GameState


def parse_target(query: dict[str, str]) -> ConnectionTarget:
    """Turn `?user=ana` / `?device=home_pi_01` / `?view=audience` into a target.

    Raises ValueError naming the value and the expected shape.
    """
    expected = "user=ana|ben, device=home_pi_01, view=audience"
    if query.get("user") in USER_IDS:
        return ConnectionTarget("mobile", user_id=query["user"])
    if query.get("device") == HOME_DEVICE_ID:
        return ConnectionTarget("home", device_id=HOME_DEVICE_ID)
    if query.get("view") == "audience":
        return ConnectionTarget("audience")
    raise ValueError(f"unknown connection query {query!r}; expected one of {expected}")


class ConnectionService:
    """Accepts clients and sends them the snapshot they are allowed to see."""

    def __init__(self, hub: EventHub, store: SessionStore, live_hint: LiveHint) -> None:
        self._hub = hub
        self._store = store
        self._live_hint = live_hint

    async def accept(self, target: ConnectionTarget, sender: Sender) -> Connection | None:
        """Send session state, activity state and any live hint, then register; None if gone."""
        return await self._hub.connect(target, sender, self._snapshot)

    def _snapshot(self) -> list[tuple[EventType, EventPayload]]:
        events: list[tuple[EventType, EventPayload]] = [
            (EventType.SESSION_STATE_CHANGED, self._store.session_state()),
            (EventType.ACTIVITY_STATE_CHANGED, self._store.activity),
        ]
        prompt = self._store.private_prompt
        if prompt is not None and self._store.activity.state is GameState.ACTIVE_ROUND:
            # The hub's delivery rules send this to the Home connection only.
            events.append((EventType.ACTIVITY_PRIVATE_PROMPT, prompt))
        if self._live_hint.current is not None:
            events.append((EventType.HINT_CREATED, self._live_hint.current))
        return events

    def close(self, connection: Connection) -> None:
        """Forget a client that went away."""
        self._hub.unregister(connection)
