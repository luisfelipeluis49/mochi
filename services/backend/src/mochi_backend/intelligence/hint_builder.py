"""Turns a matched word into a Hint and its DISCOVERED learning event."""

from dataclasses import dataclass
from datetime import timedelta

from mochi_backend.intelligence.lexicon import LexiconEntry, other_language
from mochi_backend.intelligence.word_owner import owner_for
from mochi_backend.platform.clock import Clock, iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_contracts import (
    Hint,
    LearningEvent,
    LearningState,
    Reason,
    SessionContext,
    StateChange,
)


@dataclass(frozen=True)
class CaseMatch:
    """What a rule or the model found: the word to show and why."""

    reason: Reason
    expression: str
    meaning: str | None
    example: str | None


def match_from_entry(entry: LexiconEntry, reason: Reason, context: SessionContext) -> CaseMatch:
    """Show the focus-language word, with the other language as its meaning."""
    return CaseMatch(
        reason=reason,
        expression=entry.word(context.focus),
        meaning=entry.word(other_language(context.focus)),
        example=entry.example(context.focus),
    )


class HintFactory:
    """Creates ids and timestamps. Example: `HintFactory(clock, ids, 8.0).hint_for(match, ctx)`."""

    def __init__(self, clock: Clock, ids: IdGenerator, ttl_seconds: float) -> None:
        self._clock = clock
        self._ids = ids
        self._ttl = ttl_seconds

    def hint_for(self, match: CaseMatch, context: SessionContext) -> Hint:
        """Build the Hint; it expires `ttl_seconds` after now."""
        expires = self._clock.now() + timedelta(seconds=self._ttl)
        return Hint(
            hint_id=self._ids.new("hint"),
            target_user_id=owner_for(context),
            target_language=context.focus,
            expression=match.expression,
            meaning=match.meaning,
            example=match.example,
            reason=match.reason,
            expires_at=iso_z(expires),
        )

    def event_for(self, hint: Hint) -> LearningEvent:
        """The DISCOVERED learning event for a hint (created the moment it is shown)."""
        first = StateChange(learning_state=LearningState.DISCOVERED, at=iso_z(self._clock.now()))
        return LearningEvent(
            learning_event_id=self._ids.new("learn"),
            user_id=hint.target_user_id,
            target_language=hint.target_language,
            expression=hint.expression,
            meaning=hint.meaning,
            detection_signal=hint.reason,
            hint_id=hint.hint_id,
            learning_state=LearningState.DISCOVERED,
            state_history=[first],
        )


def already_saved(hint: Hint, context: SessionContext) -> bool:
    """True when that person already has this expression saved (no duplicate card)."""
    wanted = hint.expression.lower()
    saved = [e for events in context.learning_events.values() for e in events]
    return any(e.user_id == hint.target_user_id and e.expression.lower() == wanted for e in saved)
