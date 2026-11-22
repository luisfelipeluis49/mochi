"""A phrase Mochi taught becomes something to practise (DECISIONS D-61).

Training is meant to hold what a person had a hard time saying or understanding, and that is often
a whole phrase, not one word: "how do I say my sneakers are nice?". The character writes a silent
`[phrase: my sneakers are nice | meus tênis são bonitos]` next to the line it speaks (the gateway
strips every bracket before anything is said). The phrase is in the language the person learns, the
meaning in their own; it is saved for the person learning that language (AGENTS 7.3).
"""

import re
from collections.abc import Callable

from mochi_backend.intelligence.hint_builder import HintFactory
from mochi_contracts import Decision, Language, LearningEvent, SessionContext

_PHRASE = re.compile(r"\[\s*phrase\b\s*:?\s*([^|\]]{2,120}?)\s*\|\s*([^\]]{2,120}?)\s*\]", re.I)
MAX_PHRASES = 2  # a line teaches one thing; more is the model rambling
MAX_WORDS = 12  # a phrase, not a paragraph


def phrases_in(line: str) -> list[tuple[str, str]]:
    """The (phrase, meaning) pairs written in `line`, at most `MAX_PHRASES`.

    Example: `phrases_in("[phrase: hi | oi] Try!")` gives `[("hi", "oi")]`.
    """
    found = [(m.group(1).strip(), m.group(2).strip()) for m in _PHRASE.finditer(line)]
    return [(p, m) for p, m in found if len(p.split()) <= MAX_WORDS][:MAX_PHRASES]


class PhraseSaver:
    """Adds the phrases Mochi taught to a decision's learning events."""

    def __init__(
        self, factory: HintFactory, language_of: Callable[[str, Language], Language]
    ) -> None:
        self._factory = factory
        self._language_of = language_of

    def add_to(self, decision: Decision, context: SessionContext) -> Decision:
        """The decision with a DISCOVERED event for each new phrase in what Mochi says."""
        if decision.speak is None:
            return decision
        saved = [
            e for e in (self._event(p, m, context) for p, m in phrases_in(decision.speak.text)) if e
        ]
        if not saved:
            return decision
        return decision.model_copy(update={"learning_events": [*decision.learning_events, *saved]})

    def _event(self, phrase: str, meaning: str, context: SessionContext) -> LearningEvent | None:
        language = self._language_of(phrase, context.focus)
        learners = [p.user_id for p in context.participants if p.target_language == language]
        if len(learners) != 1 or _already_saved(learners[0], phrase, context):
            return None
        return self._factory.phrase_event(learners[0], language, phrase, meaning)


def _already_saved(user_id: str, phrase: str, context: SessionContext) -> bool:
    wanted = phrase.lower()
    saved = [e for events in context.learning_events.values() for e in events]
    return any(e.user_id == user_id and e.expression.lower() == wanted for e in saved)
