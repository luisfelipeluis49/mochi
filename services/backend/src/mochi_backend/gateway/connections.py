"""A client connects: register it, then send the current state as normal enveloped events."""

from collections.abc import Callable
from dataclasses import dataclass

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import Connection, EventHub, Sender
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.roster import HOME_DEVICE_ID, SESSION_ID, Roster
from mochi_backend.gateway.session_registry import SessionRegistry
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.team.ledger import TeamLedger
from mochi_contracts import EventPayload, EventType

SURFACES = ("ar",)
EXPECTED = "user={who}[&surface=ar][&session=ID], device=home_pi_01, view=audience[&session=ID]"
NAMED_IDS = 4  # a close reason is short: name the people only while they are this few
ECHO_LIMIT = 16  # a WebSocket close reason may be at most 123 bytes
REPORTS_ON_CONNECT = 5  # a person's newest reports; the rest is `GET /api/users/{id}/reports`


def _echo(value: str) -> str:
    return value if len(value) <= ECHO_LIMIT else value[:ECHO_LIMIT] + "..."


def _expected(roster: Roster) -> str:
    """The shapes a query may have, naming the known people when they are few."""
    ids = roster.user_ids()
    named = "|".join(ids) if len(ids) <= NAMED_IDS else "ID"
    return EXPECTED.format(who=f"{named}|<user_id>")  # ... or a user the web app made (D-56)


def _nobody_else(user_id: str) -> bool:
    return False


def parse_target(
    query: dict[str, str],
    roster: Roster | None = None,
    may_connect: Callable[[str], bool] = _nobody_else,
) -> ConnectionTarget:
    """Turn `?user=ana[&surface=ar][&session=ID]`, `?device=home_pi_01` or `?view=audience` into a
    target. `session` names the session a phone, glasses or projector follows (default: the Pi's).
    `roster`: the company's people (default: the two demo people). `may_connect` says which other
    users exist (the user directory's: a person the web app made, D-56); `guest` and unknown
    users are refused.

    Raises ValueError naming the value and the expected shape.
    Example: `parse_target({"user": "ana"}).kind` is `"mobile"`.
    """
    known = roster or Roster()
    session = query.get("session", SESSION_ID)
    if not SessionRegistry.is_valid_id(session):
        raise ValueError(f"bad session id {_echo(session)!r}; use letters, digits, - and _")
    if "surface" in query and query["surface"] not in SURFACES:
        raise ValueError(f"unknown surface {_echo(query['surface'])!r}; expected surface=ar")
    if known.knows(query.get("user")) or may_connect(query.get("user", "")):
        if query.get("surface") == "ar":
            return ConnectionTarget("glasses", user_id=query["user"], session_id=session)
        return ConnectionTarget("mobile", user_id=query["user"], session_id=session)
    if "surface" not in query and query.get("device") == HOME_DEVICE_ID:
        return ConnectionTarget("home", device_id=HOME_DEVICE_ID)
    if "surface" not in query and query.get("view") == "audience":
        return ConnectionTarget("audience", session_id=session)
    shown = {k: _echo(v) for k, v in list(query.items()) if k not in ("surface", "session")}
    shown = dict(list(shown.items())[:1])
    raise ValueError(f"unknown connection query {shown!r}; expected one of {_expected(known)}")


@dataclass(frozen=True)
class WhoConnects:
    """Who may open a socket, and what of theirs is kept: the company's people (`roster`), the
    users the web app made (`may_connect`, D-56), and the reports in the `ledger` (D-54)."""

    roster: Roster
    ledger: TeamLedger | None = None
    may_connect: Callable[[str], bool] = _nobody_else


class ConnectionService:
    """Accepts clients and sends them the snapshot they are allowed to see."""

    def __init__(
        self, hub: EventHub, words: IntelligencePort, registry: SessionRegistry, who: WhoConnects
    ) -> None:
        self._hub = hub
        self._words = words
        self._registry = registry
        self._roster = who.roster
        self._ledger = who.ledger
        self._may_connect = who.may_connect

    def target_for(self, query: dict[str, str]) -> ConnectionTarget:
        """`parse_target` over the people known now. Example: `target_for({"user": "ana"})`."""
        return parse_target(query, self._roster, self._may_connect)

    async def accept(self, target: ConnectionTarget, sender: Sender) -> Connection | None:
        """Send session state, any live hint, saved words and newest reports, then register.

        The state is that of the session the client follows; before its Start there is none yet,
        so it sees an idle one and gets the real events once the session begins. Saved words are
        sent as `learning_event.created`, oldest first; the hub's delivery rules give each phone
        only its own person's words. Returns None if the client is gone.
        """
        runtime = self._registry.peek(target.session_id)
        scoped = runtime.core.hub if runtime else self._hub.for_session(target.session_id)
        return await scoped.connect(target, sender, lambda: self._snapshot(target))

    def _snapshot(self, target: ConnectionTarget) -> list[tuple[EventType, EventPayload]]:
        runtime = self._registry.peek(target.session_id)
        store = runtime.core.store if runtime else SessionStore(self._roster)
        events: list[tuple[EventType, EventPayload]] = [
            (EventType.SESSION_STATE_CHANGED, store.session_state()),
        ]
        if runtime and runtime.core.live_hint.current is not None:
            events.append((EventType.HINT_CREATED, runtime.core.live_hint.current))
        if target.user_id is not None:  # only that person's own; screens get none (D-56)
            saved = reversed(self._words.words_for(target.user_id))
            events += [(EventType.LEARNING_EVENT_CREATED, word) for word in saved]
            events += self._reports(target.user_id)
        return events

    def _reports(self, user_id: str) -> list[tuple[EventType, EventPayload]]:
        """That person's newest reports, oldest first."""
        if self._ledger is None:
            return []
        kind = EventType.CONVERSATION_REPORT_CREATED
        return [(kind, report) for report in self._ledger.reports_by(user_id)[-REPORTS_ON_CONNECT:]]

    def close(self, connection: Connection) -> None:
        """Forget a client that went away."""
        self._hub.unregister(connection)
