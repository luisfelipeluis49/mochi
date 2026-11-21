"""A client connects: register it, then send the current state as normal enveloped events."""

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import Connection, EventHub, Sender
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.roster import HOME_DEVICE_ID, USER_IDS
from mochi_backend.gateway.session_store import SessionStore
from mochi_contracts import EventPayload, EventType


SURFACES = ("ar",)
EXPECTED = "user=ana|ben[&surface=ar], device=home_pi_01, view=audience"
ECHO_LIMIT = 16  # a WebSocket close reason may be at most 123 bytes


def _echo(value: str) -> str:
    return value if len(value) <= ECHO_LIMIT else value[:ECHO_LIMIT] + "..."


def parse_target(query: dict[str, str]) -> ConnectionTarget:
    """Turn `?user=ana` / `?user=ana&surface=ar` / `?device=home_pi_01` / `?view=audience` into a target.

    Raises ValueError naming the value and the expected shape.
    """
    if "surface" in query and query["surface"] not in SURFACES:
        raise ValueError(f"unknown surface {_echo(query['surface'])!r}; expected surface=ar")
    if query.get("user") in USER_IDS:
        kind = "glasses" if query.get("surface") == "ar" else "mobile"
        return ConnectionTarget(kind, user_id=query["user"])
    if "surface" not in query and query.get("device") == HOME_DEVICE_ID:
        return ConnectionTarget("home", device_id=HOME_DEVICE_ID)
    if "surface" not in query and query.get("view") == "audience":
        return ConnectionTarget("audience")
    shown = {k: _echo(v) for k, v in list(query.items()) if k != "surface"}
    shown = dict(list(shown.items())[:1])
    raise ValueError(f"unknown connection query {shown!r}; expected one of {EXPECTED}")


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
        if self._live_hint.current is not None:
            events.append((EventType.HINT_CREATED, self._live_hint.current))
        return events

    def close(self, connection: Connection) -> None:
        """Forget a client that went away."""
        self._hub.unregister(connection)
