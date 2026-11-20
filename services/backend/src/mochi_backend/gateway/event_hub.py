"""The hub: the only publisher. It sets every envelope field and routes per connection."""

import asyncio
from dataclasses import dataclass
from typing import Protocol

from mochi_backend.gateway.delivery_rules import ConnectionTarget, hint_user_of, is_recipient
from mochi_backend.gateway.roster import SESSION_ID
from mochi_backend.gateway.secret_guard import SecretGuard
from mochi_backend.platform.clock import Clock, iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import (
    SCHEMA_VERSION,
    Activity,
    Envelope,
    EventPayload,
    EventType,
    GameState,
    HintCleared,
    PrivatePrompt,
)

# A phone that stops reading must not hold up the others or the reply to Agora.
DEFAULT_SEND_TIMEOUT_SECONDS = 1.0


class Sender(Protocol):
    """Anything that can push text to one client (a WebSocket in production)."""

    async def send_text(self, text: str) -> None:
        """Send one message; raises ConnectionError when the client is gone."""
        ...


@dataclass(frozen=True)
class Connection:
    """A registered client."""

    target: ConnectionTarget
    sender: Sender


class EventHub:
    """Registry of connections plus the single global sequence counter."""

    def __init__(
        self,
        clock: Clock,
        ids: IdGenerator,
        logger: EventLogger,
        send_timeout_seconds: float = DEFAULT_SEND_TIMEOUT_SECONDS,
    ) -> None:
        self._clock = clock
        self._ids = ids
        self._logger = logger
        self._connections: list[Connection] = []
        self._sequence = 0
        self._hint_users: dict[str, str | None] = {}
        self._secrets = SecretGuard()
        self._lock = asyncio.Lock()  # one publish at a time keeps sequences in delivery order
        self._send_timeout = send_timeout_seconds

    def register(self, target: ConnectionTarget, sender: Sender) -> Connection:
        """Add a client. Example: `hub.register(ConnectionTarget("mobile", user_id="ana"), ws)`."""
        connection = Connection(target, sender)
        self._connections.append(connection)
        return connection

    def unregister(self, connection: Connection) -> None:
        """Remove a client (idempotent)."""
        self._connections = [c for c in self._connections if c is not connection]

    def protect_secret(self, word: str) -> None:
        """Treat `word` as a secret until the round result is published."""
        self._secrets.protect(word)

    def forget_secrets(self) -> None:
        """Stop protecting round secrets (the round ended without a result, e.g. on Stop)."""
        self._secrets.clear()

    def reset(self) -> None:
        """Forget hint routing and secrets (demo reset). Sequence keeps counting up."""
        self._hint_users.clear()
        self._secrets.clear()

    async def publish(self, event_type: EventType, payload: EventPayload) -> Envelope:
        """Wrap `payload` in an envelope and send it to every connection entitled to it."""
        async with self._lock:
            envelope = self._envelope(event_type, self._prepared(event_type, payload))
            await asyncio.gather(*(self._deliver(c, envelope) for c in list(self._connections)))
            self._log(envelope)
            return envelope

    async def send_to(
        self, connection: Connection, event_type: EventType, payload: EventPayload
    ) -> None:
        """Send one event to one connection (used for the snapshot on connect)."""
        async with self._lock:
            envelope = self._envelope(event_type, self._prepared(event_type, payload))
            await self._deliver(connection, envelope)

    def _prepared(self, event_type: EventType, payload: EventPayload) -> EventPayload:
        if isinstance(payload, PrivatePrompt):
            self.protect_secret(payload.secret_word)
        if isinstance(payload, Activity) and event_type is EventType.ACTIVITY_STATE_CHANGED:
            return self._public_activity(payload)
        return payload

    def _public_activity(self, activity: Activity) -> Activity:
        if activity.state is not GameState.ACTIVE_ROUND:
            self._secrets.clear()  # the round is over: the word may be shown
            return activity
        if activity.revealed_word is None and not self._secrets.leaks(activity):
            return activity
        self._logger.log("secret_leak_blocked", {"round_id": activity.round_id, "error": "leak"})
        return activity.model_copy(
            update={"revealed_word": None, "public_instruction": "A round is in progress."}
        )

    def _envelope(self, event_type: EventType, payload: EventPayload) -> Envelope:
        self._sequence += 1
        if event_type is EventType.HINT_CREATED:
            self._hint_users[getattr(payload, "hint_id", "")] = hint_user_of(payload)
        return Envelope(
            schema_version=SCHEMA_VERSION,
            event_id=self._ids.new("evt"),
            type=event_type,
            session_id=SESSION_ID,
            emitted_at=iso_z(self._clock.now()),
            sequence=self._sequence,
            payload=payload,
        )

    def _hint_user(self, envelope: Envelope) -> str | None:
        if isinstance(envelope.payload, HintCleared):
            return self._hint_users.get(envelope.payload.hint_id)
        return hint_user_of(envelope.payload)

    async def _deliver(self, connection: Connection, envelope: Envelope) -> None:
        hint_user = self._hint_user(envelope)
        if not is_recipient(envelope.type, envelope.payload, connection.target, hint_user):
            return
        text = envelope.model_dump_json()
        if connection.target.kind == "audience" and self._secrets.leaks(envelope.payload):
            self._logger.log("secret_leak_blocked", {"type": envelope.type.value, "error": "leak"})
            return
        try:
            await asyncio.wait_for(connection.sender.send_text(text), self._send_timeout)
        except (ConnectionError, RuntimeError, OSError, TimeoutError) as error:
            self._logger.log("connection_dropped", {"reason": repr(error)})
            self.unregister(connection)

    def _log(self, envelope: Envelope) -> None:
        self._logger.log(
            "event_published",
            {
                "type": envelope.type.value,
                "sequence": envelope.sequence,
                "event_id": envelope.event_id,
                "connections": len(self._connections),
            },
        )
