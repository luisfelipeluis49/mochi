"""The only way the gateway reaches intelligence (AGENTS 6.5). Kauê's side implements it."""

from typing import Protocol, runtime_checkable

from mochi_backend.platform.text_sink import TextSink
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


class IntelligencePort(Protocol):
    """decide / apply / words_for, plus reset, session_started, interrupted and device_status,
    and four that look at what was said beyond the stuck word: explain, suggest, coach and
    used_alone (PROPOSAL, DECISIONS D-53 to D-55 and D-59)."""

    async def decide(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide what Mochi does with one turn."""
        ...

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or update learning events; returns the stored records."""
        ...

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """One person's saved words, newest first."""
        ...

    def reset(self) -> None:
        """Clear saved words and Mochi's conversation."""
        ...

    def session_started(
        self, conversing: bool, language: Language | None = None, explains: bool = False
    ) -> None:
        """A session begins. `conversing`: a review, where one person talks WITH Mochi; False
        for a meeting, where Mochi waits for its name.

        `language`: the one it was called in and greeted in, when known ("oi Mochi" is pt-BR).
        """
        ...

    def interrupted(self) -> None:
        """Someone talked over Mochi: it stops and goes back to just listening."""
        ...

    def device_status(
        self, volume: int | None, temperature: int | None, voices: list[str], speaker: str | None
    ) -> None:
        """What the device reports about itself (speaker level, temperature, voices it knows)."""
        ...

    async def explain(self, turn: Turn, context: SessionContext) -> TranscriptMark | None:
        """An idiom or a technical term in the sentence that the people listening may not know,
        with what it means; None for nearly every sentence. Asked after the turn was handled."""
        ...

    async def suggest(self, turn: Turn, context: SessionContext, hint: Hint) -> str | None:
        """The whole sentence the speaker was trying to say, after `hint` gave them the word
        (one-touch assistance, D-59); None when there is nothing to say for them."""
        ...

    async def coach(
        self, draft: ConversationReport, person: Participant
    ) -> ConversationReport | None:
        """After a session: the person's report with what was wrong in their sentences written
        in. `draft` holds the sentences. None when no report can be written (no model, or it
        did not answer)."""
        ...

    def used_alone(
        self, said: list[Utterance], shown: list[str], began: str
    ) -> list[LearningEvent]:
        """After a meeting: the saved words people used in it with no hint, as proposals for
        `apply` (USED_INDEPENDENTLY). `said` carries the final speakers; `shown` is every word
        a screen showed during it."""
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
