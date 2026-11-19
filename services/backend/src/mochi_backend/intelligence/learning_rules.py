"""Learning-state transitions (AGENTS 7.4)."""

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


def _turns_since(event: LearningEvent, turns: list[Turn]) -> int:
    discovered_at = parse_iso_z(event.state_history[-1].at)
    return sum(1 for t in turns if parse_iso_z(t.received_at) > discovered_at)


def _is_assisted_by(event: LearningEvent, turn: Turn, context: SessionContext) -> bool:
    if event.learning_state is not LearningState.DISCOVERED:
        return False
    if _turns_since(event, context.recent_turns) >= ASSIST_WINDOW_TURNS:
        return False
    return has_phrase(normalized(turn.text), event.expression)


def assisted_updates(turn: Turn, context: SessionContext, clock: Clock) -> list[LearningEvent]:
    """DISCOVERED words said within the next three turns, upgraded to ASSISTED (together mode)."""
    if context.mode is not SessionMode.TOGETHER:
        return []
    now = iso_z(clock.now())
    saved = [e for events in context.learning_events.values() for e in events]
    return [
        with_state(e, LearningState.ASSISTED, now)
        for e in saved
        if _is_assisted_by(e, turn, context)
    ]
