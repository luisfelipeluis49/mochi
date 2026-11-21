"""A client connects: register it, then send the current state as normal enveloped events."""

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import Connection, EventHub, Sender
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.roster import HOME_DEVICE_ID, SESSION_ID, USER_IDS
from mochi_backend.gateway.session_registry import SessionRegistry
from mochi_backend.gateway.session_store import SessionStore
from mochi_contracts import EventPayload, EventType, GameState

SURFACES = ("ar",)
EXPECTED = "user=ana|ben[&surface=ar][&session=ID], device=home_pi_01, view=audience[&session=ID]"
ECHO_LIMIT = 16  # a WebSocket close reason may be at most 123 bytes


def _echo(value: str) -> str:
    return value if len(value) <= ECHO_LIMIT else value[:ECHO_LIMIT] + "..."


def parse_target(query: dict[str, str]) -> ConnectionTarget:
    """Turn `?user=ana[&surface=ar][&session=ID]`, `?device=home_pi_01` or `?view=audience` into a
    target. `session` names the session a phone, glasses or projector follows (default: the Pi's).

    Raises ValueError naming the value and the expected shape.
    """
    session = query.get("session", SESSION_ID)
    if not SessionRegistry.is_valid_id(session):
        raise ValueError(f"bad session id {_echo(session)!r}; use letters, digits, - and _")
    if "surface" in query and query["surface"] not in SURFACES:
        raise ValueError(f"unknown surface {_echo(query['surface'])!r}; expected surface=ar")
    if query.get("user") in USER_IDS:
        if query.get("surface") == "ar":
            return ConnectionTarget("glasses", user_id=query["user"], session_id=session)
        return ConnectionTarget("mobile", user_id=query["user"], session_id=session)
    if "surface" not in query and query.get("device") == HOME_DEVICE_ID:
        return ConnectionTarget("home", device_id=HOME_DEVICE_ID)
    if "surface" not in query and query.get("view") == "audience":
        return ConnectionTarget("audience", session_id=session)
    shown = {k: _echo(v) for k, v in list(query.items()) if k not in ("surface", "session")}
    shown = dict(list(shown.items())[:1])
    raise ValueError(f"unknown connection query {shown!r}; expected one of {EXPECTED}")


class ConnectionService:
    """Accepts clients and sends them the snapshot they are allowed to see."""

    def __init__(self, hub: EventHub, words: IntelligencePort, registry: SessionRegistry) -> None:
        self._hub = hub
        self._words = words
        self._registry = registry

    async def accept(self, target: ConnectionTarget, sender: Sender) -> Connection | None:
        """Send session state, activity state, any live hint and saved words, then register.

        The state is that of the session the client follows; before its Start there is none yet,
        so it sees an idle one and gets the real events once the session begins. Saved words are
        sent as `learning_event.created`, oldest first; the hub's delivery rules give each phone
        only its own person's words. Returns None if the client is gone.
        """
        scoped = self._hub.for_session(target.session_id)  # its events carry its session
        return await scoped.connect(target, sender, lambda: self._snapshot(target.session_id))

    def _snapshot(self, session_id: str) -> list[tuple[EventType, EventPayload]]:
        runtime = self._registry.peek(session_id)
        store = runtime.core.store if runtime else SessionStore()
        events: list[tuple[EventType, EventPayload]] = [
            (EventType.SESSION_STATE_CHANGED, store.session_state()),
            (EventType.ACTIVITY_STATE_CHANGED, store.activity),
        ]
        prompt = store.private_prompt
        if prompt is not None and store.activity.state is GameState.ACTIVE_ROUND:
            # The hub's delivery rules send this to the Home connection only.
            events.append((EventType.ACTIVITY_PRIVATE_PROMPT, prompt))
        if runtime and runtime.core.live_hint.current is not None:
            events.append((EventType.HINT_CREATED, runtime.core.live_hint.current))
        for user in USER_IDS:
            saved = reversed(self._words.words_for(user))
            events += [(EventType.LEARNING_EVENT_CREATED, word) for word in saved]
        return events

    def close(self, connection: Connection) -> None:
        """Forget a client that went away."""
        self._hub.unregister(connection)
