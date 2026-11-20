"""Learning-state transitions (AGENTS 7.4)."""

from datetime import datetime, timedelta

from mochi_backend.intelligence.tokens import has_phrase, normalized
from mochi_backend.platform.clock import Clock, iso_z, parse_iso_z
from mochi_contracts import (
    LearningEvent,
    LearningState,
    SessionContext,
    SessionMode,
    StateChange,
    Turn,
)

# "said within the next three turns": the current turn may be the 1st, 2nd or 3rd after the hint.
ASSIST_WINDOW_TURNS = 3


def with_state(event: LearningEvent, state: LearningState, at: str) -> LearningEvent:
    """A copy of `event` in `state`, with the change appended to `state_history`.

    Example: DISCOVERED -> ASSISTED gives a history of two entries.
    """
    history = [*event.state_history, StateChange(learning_state=state, at=at)]
    return event.model_copy(update={"learning_state": state, "state_history": history})


def _window_start(
    event: LearningEvent, context: SessionContext, hint_ttl_seconds: float
) -> datetime:
    """When the three-turn window opened: the discovery, or the latest time the hint was shown.

    Showing the same word again creates no new card, so without this a second hint shown after
    the first window ended could never lead to ASSISTED.
    """
    start = parse_iso_z(event.state_history[-1].at)
    for hint in context.recent_hints:
        if hint.expression == event.expression:
            shown_at = parse_iso_z(hint.expires_at) - timedelta(seconds=hint_ttl_seconds)
            start = max(start, shown_at)
    return start


def _is_assisted_by(
    event: LearningEvent, turn: Turn, context: SessionContext, hint_ttl_seconds: float
) -> bool:
    if event.learning_state is not LearningState.DISCOVERED:
        return False
    start = _window_start(event, context, hint_ttl_seconds)
    turns_since = sum(1 for t in context.recent_turns if parse_iso_z(t.received_at) > start)
    if turns_since >= ASSIST_WINDOW_TURNS:
        return False
    return has_phrase(normalized(turn.text), event.expression)


def assisted_updates(
    turn: Turn, context: SessionContext, clock: Clock, hint_ttl_seconds: float
) -> list[LearningEvent]:
    """DISCOVERED words said within the next three turns, upgraded to ASSISTED (together mode).

    The window opens when the word is discovered and again each time its hint is shown.
    """
    if context.mode is not SessionMode.TOGETHER:
        return []
    now = iso_z(clock.now())
    saved = [e for events in context.learning_events.values() for e in events]
    return [
        with_state(e, LearningState.ASSISTED, now)
        for e in saved
        if _is_assisted_by(e, turn, context, hint_ttl_seconds)
    ]
