"""An intelligence wrapper whose `decide` waits for a gate, to hold a turn mid-flight."""

import asyncio

from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_contracts import (
    ConversationReport,
    Decision,
    Hint,
    Language,
    LearningEvent,
    Participant,
    SessionContext,
    TranscriptMark,
    Turn,
    Utterance,
)


class GatedIntelligence:
    """Implements `IntelligencePort` by delegating, except `decide` waits for `gate`."""

    def __init__(self, inner: IntelligencePort) -> None:
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()
        self._inner = inner

    async def decide(self, turn: Turn, context: SessionContext) -> Decision:
        """Signal `entered`, wait for `gate`, then decide with the wrapped intelligence."""
        self.entered.set()
        await self.gate.wait()
        return await self._inner.decide(turn, context)

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Delegate."""
        return self._inner.apply(proposals)

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """Delegate."""
        return self._inner.words_for(user_id)

    def reset(self) -> None:
        """Delegate."""
        self._inner.reset()

    def session_started(
        self, conversing: bool, language: Language | None = None, explains: bool = False
    ) -> None:
        """Delegate."""
        self._inner.session_started(conversing, language, explains)

    def interrupted(self) -> None:
        """Delegate."""
        self._inner.interrupted()

    def device_status(
        self, volume: int | None, temperature: int | None, voices: list[str], speaker: str | None
    ) -> None:
        """Delegate."""
        self._inner.device_status(volume, temperature, voices, speaker)

    async def explain(self, turn: Turn, context: SessionContext) -> TranscriptMark | None:
        """Delegate."""
        return await self._inner.explain(turn, context)

    async def coach(
        self, draft: ConversationReport, person: Participant
    ) -> ConversationReport | None:
        """Delegate."""
        return await self._inner.coach(draft, person)

    def used_alone(
        self, said: list[Utterance], shown: list[str], began: str
    ) -> list[LearningEvent]:
        """Delegate."""
        return self._inner.used_alone(said, shown, began)

    async def suggest(self, turn: Turn, context: SessionContext, hint: Hint) -> str | None:
        """Delegate."""
        return await self._inner.suggest(turn, context, hint)
