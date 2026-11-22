"""The hub: the only publisher. It sets every envelope field and routes per connection."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from mochi_backend.gateway.delivery_rules import (
    PERSONAL_EVENTS,
    ConnectionTarget,
    hint_user_of,
    is_recipient,
)
from mochi_backend.gateway.roster import SESSION_ID
from mochi_backend.platform.clock import Clock, iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import (
    SCHEMA_VERSION,
    Envelope,
    EventPayload,
    EventType,
    HintCleared,
)

# A phone that stops reading must not hold up the others or the reply to Agora.
DEFAULT_SEND_TIMEOUT_SECONDS = 1.0


class Sender(Protocol):
    """Anything that can push text to one client (a WebSocket in production)."""

    async def send_text(self, text: str) -> None:
        """Send one message; raises ConnectionError when the client is gone."""
        ...


@dataclass
class _Shared:
    """What every session's hub view has in common: the clients, the counter, the lock."""

    connections: list["Connection"] = field(default_factory=list)
    sequence: int = 0
    hint_users: dict[str, str | None] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass(frozen=True)
class _Scope:
    """Which session a hub view publishes for, and the state all views share."""

    session_id: str
    shared: _Shared


@dataclass(frozen=True)
class Connection:
    """A registered client."""

    target: ConnectionTarget
    sender: Sender


@dataclass(frozen=True)
class _Outbound:
    """One envelope, serialized once for every client."""

    envelope: Envelope
    text: str


SnapshotSource = Callable[[], list[tuple[EventType, EventPayload]]]


class EventHub:
    """The publisher for one session; views for other sessions share its clients and counter.

    `hub.for_session("p-1")` is another publisher over the same clients: an event goes only to the
    clients that joined that session, so two sessions never see each other's hints. A learning
    event is the exception: it belongs to a person, so it reaches that
    person's phone in every session (saved words are the one thing the sessions share).
    """

    def __init__(
        self,
        clock: Clock,
        ids: IdGenerator,
        logger: EventLogger,
        send_timeout_seconds: float = DEFAULT_SEND_TIMEOUT_SECONDS,
        scope: "_Scope | None" = None,
    ) -> None:
        self._clock = clock
        self._ids = ids
        self._logger = logger
        scope = scope or _Scope(SESSION_ID, _Shared())
        self._session_id = scope.session_id
        self._shared = scope.shared
        self._send_timeout = send_timeout_seconds

    def for_session(self, session_id: str) -> "EventHub":
        """A publisher for `session_id` over the same clients, counter and lock."""
        return EventHub(
            self._clock,
            self._ids,
            self._logger,
            self._send_timeout,
            _Scope(session_id, self._shared),
        )

    def register(self, target: ConnectionTarget, sender: Sender) -> Connection:
        """Add a client. Example: `hub.register(ConnectionTarget("mobile", user_id="ana"), ws)`."""
        connection = Connection(target, sender)
        self._shared.connections.append(connection)
        return connection

    @property
    def connection_count(self) -> int:
        """How many clients are registered right now (in every session)."""
        return len(self._shared.connections)

    def unregister(self, connection: Connection) -> None:
        """Remove a client (idempotent)."""
        self._shared.connections[:] = [c for c in self._shared.connections if c is not connection]

    def reset(self) -> None:
        """Forget hint routing (demo reset). Sequence keeps counting up."""
        self._shared.hint_users.clear()

    async def publish(self, event_type: EventType, payload: EventPayload) -> Envelope:
        """Wrap `payload` in an envelope and send it to every connection entitled to it."""
        async with self._shared.lock:
            outbound = self._outbound(event_type, payload)
            await asyncio.gather(
                *(self._deliver(c, outbound) for c in list(self._shared.connections))
            )
            self._log(outbound.envelope)
            return outbound.envelope

    async def connect(
        self, target: ConnectionTarget, sender: Sender, snapshot: SnapshotSource
    ) -> Connection | None:
        """Send `snapshot()` to a new client, then start broadcasting to it; None if it is gone.

        All under the publish lock: the snapshot is read after any publish in flight has finished
        and the client is registered before the next one starts, so it sees each event once and
        in order. A dead client is dropped at its first failed send, not after three.
        """
        async with self._shared.lock:
            connection = Connection(target, sender)
            if not await self._send_snapshot(connection, snapshot()):
                return None
            self._shared.connections.append(connection)
            return connection

    async def _send_snapshot(
        self, connection: Connection, events: list[tuple[EventType, EventPayload]]
    ) -> bool:
        for event_type, payload in events:
            if not await self._deliver(connection, self._outbound(event_type, payload)):
                return False
        return True

    def _outbound(self, event_type: EventType, payload: EventPayload) -> _Outbound:
        envelope = self._envelope(event_type, payload)
        return _Outbound(envelope, envelope.model_dump_json())  # once per event, not per client

    def _envelope(self, event_type: EventType, payload: EventPayload) -> Envelope:
        self._shared.sequence += 1
        if event_type is EventType.HINT_CREATED:
            self._shared.hint_users[getattr(payload, "hint_id", "")] = hint_user_of(payload)
        return Envelope(
            schema_version=SCHEMA_VERSION,
            event_id=self._ids.new("evt"),
            type=event_type,
            session_id=self._session_id,
            emitted_at=iso_z(self._clock.now()),
            sequence=self._shared.sequence,
            payload=payload,
        )

    def _hint_user(self, envelope: Envelope) -> str | None:
        if isinstance(envelope.payload, HintCleared):
            return self._shared.hint_users.get(envelope.payload.hint_id)
        return hint_user_of(envelope.payload)

    async def _deliver(self, connection: Connection, outbound: _Outbound) -> bool:
        """Send if this client is entitled to the event. False only when the client failed."""
        envelope = outbound.envelope
        hint_user = self._hint_user(envelope)
        if not self._in_scope(envelope, connection):
            return True
        if not is_recipient(envelope.type, envelope.payload, connection.target, hint_user):
            return True
        try:
            await asyncio.wait_for(connection.sender.send_text(outbound.text), self._send_timeout)
        except (ConnectionError, RuntimeError, OSError, TimeoutError) as error:
            self._logger.log("connection_dropped", {"reason": repr(error)})
            self.unregister(connection)
            return False
        return True

    def _in_scope(self, envelope: Envelope, connection: Connection) -> bool:
        """This client is in the session the event is for; a person's words and reports reach
        them anywhere."""
        if envelope.type in PERSONAL_EVENTS:
            return True
        return connection.target.session_id == self._session_id

    def _log(self, envelope: Envelope) -> None:
        self._logger.log(
            "event_published",
            {
                "type": envelope.type.value,
                "session_id": self._session_id,
                "sequence": envelope.sequence,
                "event_id": envelope.event_id,
                "connections": len(self._shared.connections),
            },
        )
