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
    Utterance,
)

# "said within the next three turns": the current turn may be the 1st, 2nd or 3rd after the hint.
ASSIST_WINDOW_TURNS = 3
# ... and those three turns are counted from this session's turns only, so a card from last week
# said in the first sentences of a new meeting looked "used with help" with no hint in sight.
# Three turns of talk take well under this (DECISIONS D-55).
ASSIST_WINDOW = timedelta(minutes=3)


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
    if parse_iso_z(turn.received_at) - start > ASSIST_WINDOW:
        return False  # shown in an earlier session: said now, it was not read off the screen
    turns_since = sum(1 for t in context.recent_turns if parse_iso_z(t.received_at) > start)
    if turns_since >= ASSIST_WINDOW_TURNS:
        return False
    return has_phrase(normalized(turn.text), event.expression)


def assisted_updates(
    turn: Turn, context: SessionContext, clock: Clock, hint_ttl_seconds: float
) -> list[LearningEvent]:
    """DISCOVERED words said within the next three turns, upgraded to ASSISTED (meeting mode).

    The window opens when the word is discovered and again each time its hint is shown.
    """
    if context.mode is not SessionMode.MEETING:
        return []
    now = iso_z(clock.now())
    saved = [e for events in context.learning_events.values() for e in events]
    return [
        with_state(e, LearningState.ASSISTED, now)
        for e in saved
        if _is_assisted_by(e, turn, context, hint_ttl_seconds)
    ]


REVIEWABLE = (LearningState.DISCOVERED, LearningState.ASSISTED)
REVIEW_LIMIT = 6  # words handed to Mochi for one review: the newest that are not recalled yet


def words_to_review(context: SessionContext) -> list[LearningEvent]:
    """The reviewer's saved words not yet recalled, newest first; empty outside a review.

    Example: Ana's "postpone" (DISCOVERED) is in it; her "umbrella" (REINFORCED) is not.
    """
    if context.mode is not SessionMode.REVIEW or not context.participants:
        return []
    mine = context.learning_events.get(context.participants[0].user_id, [])
    return [e for e in mine if e.learning_state in REVIEWABLE][:REVIEW_LIMIT]


def recalled_updates(turn: Turn, context: SessionContext, clock: Clock) -> list[LearningEvent]:
    """A review: a saved word the person says by themselves becomes REINFORCED (AGENTS 7.4).

    Not a word shown as a hint a moment ago: reading it off the screen is not recalling it.
    Example: Ana, in a review, says "we had to postpone it" -> her "postpone" card is REINFORCED.
    """
    shown = {hint.expression.lower() for hint in context.recent_hints}
    said = normalized(turn.text)
    now = iso_z(clock.now())
    return [
        with_state(e, LearningState.REINFORCED, now)
        for e in words_to_review(context)
        if e.expression.lower() not in shown and has_phrase(said, e.expression)
    ]


ECHO_SENTENCES = 2  # a word someone else said this recently is repeated, not remembered


def _said_unprompted(said: list[Utterance], user_id: str, expression: str) -> bool:
    """True when `user_id` said the expression in a sentence that did not follow someone else
    saying it (in one of the two sentences before)."""
    for place, sentence in enumerate(said):
        if sentence.user_id != user_id or not has_phrase(normalized(sentence.text), expression):
            continue
        before = said[max(0, place - ECHO_SENTENCES) : place]
        echoed = (s for s in before if s.user_id != user_id)
        if not any(has_phrase(normalized(s.text), expression) for s in echoed):
            return True
    return False


def used_alone(
    cards: list[LearningEvent], said: list[Utterance], shown: set[str], began: datetime, at: str
) -> list[LearningEvent]:
    """One person's saved words they used on their own in a meeting that has just ended: each
    becomes USED_INDEPENDENTLY, "Used on your own" (AGENTS 7.4, DECISIONS D-55).

    A card counts when it was last touched before the meeting (`began`), its word was shown to
    nobody during it (`shown`, lower case), and the person's own voice said it without
    repeating a colleague. `said`: the whole meeting, every speaker, in order, with the
    speakers as settled at its end. Example: Ana was shown "postpone" on Monday; on Thursday
    her voice says "let's postpone it" -> her card reads "Used on your own".
    """
    return [
        with_state(card, LearningState.USED_INDEPENDENTLY, at)
        for card in cards
        if card.user_id is not None
        and card.learning_state is not LearningState.USED_INDEPENDENTLY
        and card.expression.lower() not in shown
        and parse_iso_z(card.state_history[-1].at) < began
        and _said_unprompted(said, card.user_id, card.expression)
    ]
