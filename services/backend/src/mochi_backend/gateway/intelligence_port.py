"""The only way the gateway reaches intelligence (AGENTS 6.5). Kauê's side implements it."""

from typing import Protocol, runtime_checkable

from mochi_backend.platform.text_sink import TextSink
from mochi_contracts import (
    ActivityCommand,
    ActivityResult,
    Decision,
    Language,
    LearningEvent,
    SessionContext,
    Turn,
)


class IntelligencePort(Protocol):
    """decide / handle / apply / words_for, plus `reset` (a proposal, see DECISIONS)."""

    async def decide(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide what Mochi does with one turn."""
        ...

    def handle(self, command: ActivityCommand, context: SessionContext) -> ActivityResult:
        """Start a round or record its result; raises ValueError when it cannot apply."""
        ...

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or update learning events; returns the stored records."""
        ...

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """One person's saved words, newest first."""
        ...

    def reset(self) -> None:
        """Clear saved words and any game."""
        ...

    def session_started(
        self, woken: bool, language: Language | None = None, explains: bool = False
    ) -> None:
        """A session begins. `woken`: Mochi was called on the device; it listens for an answer.

        `language`: the one it was called in and greeted in, when known ("oi Mochi" is pt-BR).
        """
        ...

    def device_status(
        self, volume: int | None, temperature: int | None, voices: list[str], speaker: str | None
    ) -> None:
        """What the device reports about itself (speaker level, temperature, voices it knows)."""
        ...


@runtime_checkable
class StreamingDecider(Protocol):
    """PROPOSAL (DECISIONS D-37), internal and behind MOCHI_STREAM_REPLY: `decide` that may pass
    Mochi's free-chat line to `sink` while it is written. The returned Decision is unchanged."""

    async def decide_streaming(
        self, turn: Turn, context: SessionContext, sink: TextSink
    ) -> Decision:
        """Decide one turn, streaming a free-chat line into `sink`."""
        ...
