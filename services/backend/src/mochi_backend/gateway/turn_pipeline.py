"""One chain for every turn, whether it came from Agora or from `/dev` (AGENTS 9.2).

Order: take the text -> decide -> apply learning events -> publish -> reply -> remember -> log.
"""

import asyncio
from dataclasses import dataclass

from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.roster import USER_IDS
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.platform.clock import Clock, iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import (
    Decision,
    DecisionKind,
    EventType,
    LearningEvent,
    SessionContext,
    Speak,
    Turn,
)


@dataclass(frozen=True)
class TurnOutcome:
    """What the caller needs back: the text for Agora to speak ("" = silence) and the decision."""

    reply: str
    decision: Decision


def silent_decision() -> Decision:
    """IGNORE with nothing attached."""
    return Decision(decision=DecisionKind.IGNORE, hint=None, speak=None, learning_events=[])


@dataclass(frozen=True)
class PipelineDeps:
    """Everything the pipeline is built from (injected by the composition root)."""

    store: SessionStore
    hub: EventHub
    live_hint: LiveHint
    intelligence: IntelligencePort
    silence: SilencePolicy
    clock: Clock
    ids: IdGenerator
    logger: EventLogger
    decide_timeout_seconds: float


class TurnPipeline:
    """Handles one finished sentence. Turns are processed one at a time."""

    def __init__(self, deps: PipelineDeps) -> None:
        self._store = deps.store
        self._hub = deps.hub
        self._live_hint = deps.live_hint
        self._intelligence = deps.intelligence
        self._silence = deps.silence
        self._clock = deps.clock
        self._ids = deps.ids
        self._logger = deps.logger
        self._timeout = deps.decide_timeout_seconds
        self._lock = asyncio.Lock()

    def build_context(self) -> SessionContext:
        """The context for intelligence: history plus each person's saved words."""
        words = {user: self._intelligence.words_for(user) for user in USER_IDS}
        return self._store.context(words)

    async def handle_turn(self, text: str) -> TurnOutcome:
        """Run one turn through the whole chain and return the reply for Agora."""
        async with self._lock:
            return await self._handle(text.strip())

    async def _handle(self, text: str) -> TurnOutcome:
        if not text or not self._store.capturing:
            self._logger.log("turn_ignored_not_capturing", {"text_len": len(text)})
            return TurnOutcome("", silent_decision())
        turn = Turn(
            segment_id=self._ids.new("seg"), text=text, received_at=iso_z(self._clock.now())
        )
        self._logger.log("turn", {"segment_id": turn.segment_id, "text": text})
        decision = await self._decide(turn)
        await self._publish_results(decision)
        reply = await self._reply(decision.speak)
        self._store.remember(turn, decision.hint)
        return TurnOutcome(reply, decision)

    async def _decide(self, turn: Turn) -> Decision:
        started = self._clock.now()
        try:
            decision = await asyncio.wait_for(
                self._intelligence.decide(turn, self.build_context()), self._timeout
            )
        except TimeoutError:
            self._logger.log("decide_failed", {"segment_id": turn.segment_id, "error": "timeout"})
            return silent_decision()
        except Exception as error:  # noqa: BLE001 - one bad turn must not stop the session
            self._logger.log("decide_failed", {"segment_id": turn.segment_id, "error": repr(error)})
            return silent_decision()
        millis = (self._clock.now() - started).total_seconds() * 1000
        self._log_decision(turn, decision, millis)
        return decision

    def _log_decision(self, turn: Turn, decision: Decision, millis: float) -> None:
        reason = decision.hint.reason.value if decision.hint else None
        self._logger.log(
            "decision",
            {
                "segment_id": turn.segment_id,
                "decision": decision.decision.value,
                "reason": reason,
                "latency_ms": round(millis, 1),
            },
        )

    async def _publish_results(self, decision: Decision) -> None:
        await self.save_learning_events(decision.learning_events)
        if decision.hint is not None:
            await self._live_hint.show(decision.hint)

    async def save_learning_events(self, proposals: list[LearningEvent]) -> None:
        """`apply()` the proposals, then publish `created` (first state) or `updated`."""
        for stored in self._intelligence.apply(proposals):
            first = len(stored.state_history) == 1
            kind = EventType.LEARNING_EVENT_CREATED if first else EventType.LEARNING_EVENT_UPDATED
            await self._hub.publish(kind, stored)

    async def _reply(self, speak: Speak | None) -> str:
        if speak is None:
            return ""
        await self._hub.publish(EventType.AGENT_SPEAK_REQUESTED, speak)
        self._silence.begin_speaking(speak.text)
        return speak.text
