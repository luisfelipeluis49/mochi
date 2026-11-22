"""In a web session the guest is nobody: what the rules give to the guest is the person's to learn.

A web session has the person and a `guest` with the opposite languages (D-56), so that the
whose-word rule (AGENTS 7.3) still works. When the person says a word of their own language inside
a sentence, the rules name the guest as the learner and give the pair as "their language, then the
meaning": `tênis (sneakers)` for someone learning English. That card is useless to the person, who
needs `sneakers (tênis)`. D-60 hands the pair to the person with the two sides swapped.
"""

from mochi_backend.gateway.roster import GUEST_ID
from mochi_contracts import Decision, Hint, Language, LearningEvent


def hand_guest_words_to_person(
    decision: Decision, user_id: str | None, practised: Language | None
) -> Decision:
    """The decision with every guest-owned word turned into the person's own, swapped.

    A word with no meaning cannot be swapped and is dropped (the guest is nobody).
    Example: a hint `postpone (adiar)` for the guest of a person practising Portuguese becomes
    `adiar (postpone)` in Portuguese, for the person.
    """
    if user_id is None or practised is None:
        return decision
    hint = _hint_for(decision.hint, user_id, practised)
    events = [e for e in (_event_for(e, user_id, practised) for e in decision.learning_events) if e]
    return decision.model_copy(update={"hint": hint, "learning_events": events})


def _hint_for(hint: Hint | None, user_id: str, practised: Language) -> Hint | None:
    if hint is None or hint.target_user_id != GUEST_ID:
        return hint
    if not hint.meaning:
        return None
    return hint.model_copy(
        update={
            "target_user_id": user_id,
            "expression": hint.meaning,
            "meaning": hint.expression,
            "target_language": practised,
            "example": None,  # it was written in the other language
            "candidates": None,
        }
    )


def _event_for(event: LearningEvent, user_id: str, practised: Language) -> LearningEvent | None:
    if event.user_id != GUEST_ID:
        return event
    if not event.meaning:
        return None
    return event.model_copy(
        update={
            "user_id": user_id,
            "expression": event.meaning,
            "meaning": event.expression,
            "target_language": practised,
        }
    )
