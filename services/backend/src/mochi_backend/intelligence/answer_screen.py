"""The hint model's answer, screened: what may go on the screen, and what is dropped.

Moved out of `decision_flow` unchanged when the file reached its size limit; the checks
themselves live in `answer_checks`, each from a mistake seen with a real model (DECISIONS D-29).
"""

from mochi_backend.intelligence.answer_checks import (
    language_named,
    made_up,
    only_extends,
    only_the_word,
    open_ask,
    right_way_round,
    same_words,
    translates_the_question,
)
from mochi_backend.intelligence.clear_cases import asks_for_word
from mochi_backend.intelligence.hint_builder import CaseMatch
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.stuck_signs import (
    partner_lost,
    searches,
    searching_aside,
    starts_over,
    stops_short,
)
from mochi_backend.intelligence.subtle_cases import marker_for
from mochi_backend.intelligence.tokens import has_phrase, normalized
from mochi_contracts import HintCandidate, Language, Reason, SessionContext

# PROPOSAL (docs/DECISIONS.md): reasons with no single known word, where several plausible
# completions help (AGENTS 7.1 cases 5-6). Every other reason has one right answer.
_OPEN_SEARCH_REASONS = frozenset({Reason.TRAILS_OFF, Reason.RESTARTS, Reason.TALKS_AROUND})
_MAX_CANDIDATES = 3  # the primary word plus at most two more (glasses: MAX_CANDIDATES)


def _extra_candidates(answer: ModelSuggestion) -> tuple[HintCandidate, ...]:
    """The model's extra completions, deduplicated against the primary and each other.

    Example: primary "although", candidates ["although", "unfortunately", "although"] (a
    repeat) -> `(although, unfortunately)`. The primary is always first.
    """
    primary = HintCandidate(expression=answer.expression or "", meaning=answer.meaning)
    seen = [primary.expression]
    extra = [primary]
    for candidate in answer.candidates:
        word = (candidate.expression or "").strip()
        if not word or any(same_words(word, kept) for kept in seen):
            continue
        seen.append(word)
        extra.append(HintCandidate(expression=word, meaning=candidate.meaning))
        if len(extra) == _MAX_CANDIDATES:
            break
    return tuple(extra)


def _without_empty_meaning(answer: ModelSuggestion | None) -> ModelSuggestion | None:
    """Nobody said a word in an open search, so the model sometimes repeats the hint as `meaning`.

    Seen with a real model: "vou pegar o meu, hum" -> casaco, meaning "casaco". That is a hint
    without a translation, not the invention `only_extends` is there to stop.
    """
    unsaid = (*_OPEN_SEARCH_REASONS, Reason.NOT_UNDERSTOOD)
    if answer is None or answer.reason not in unsaid or not answer.meaning:
        return answer
    if not same_words(answer.meaning, answer.expression or ""):
        return answer
    return answer.model_copy(update={"meaning": None})


def _last_text(context: SessionContext) -> str | None:
    return context.recent_turns[-1].text if context.recent_turns else None


def unseen(text: str, reason: Reason, context: SessionContext) -> bool:
    """The model names a sign of being stuck that is not in the sentence (DECISIONS D-42).

    A sentence that "trails off" has to stop short, one that "restarts" has to start over, and
    a listener who "did not understand" has to say so. The model reads these into ordinary
    sentences now and then; what a pattern can check, it checks.
    Example: `unseen("I think we should go now.", Reason.TRAILS_OFF, context)` is True.
    """
    if reason is Reason.TRAILS_OFF:
        # "I need my, como é que fala, the thing for the rain": the stop is before the aside
        return not (stops_short(text, context.focus) or searches(text))
    if reason is Reason.RESTARTS:
        written = marker_for(text) is Reason.RESTARTS  # "I keep... I keep putting it off..."
        return not (written or starts_over(text) or stops_short(text, context.focus))
    if reason is Reason.NOT_UNDERSTOOD:
        said_so = marker_for(text) is Reason.NOT_UNDERSTOOD  # "Sorry, what did you mean by..."
        return not (said_so or partner_lost(text, _last_text(context)))
    return False


def already_said(answer: ModelSuggestion, context: SessionContext) -> bool:
    """The "word they needed" is in the sentence that was not understood: nobody lacked it.

    Seen with a real model: "Do you want to go to the beach tomorrow?", "Sorry, what?" got the
    hint "beach". The listener did not hear; the speaker had the word.
    """
    before = _last_text(context)
    if answer.reason is not Reason.NOT_UNDERSTOOD or before is None:
        return False
    return has_phrase(normalized(before), answer.expression or "")


class AnswerScreen:
    """Example: `AnswerScreen(0.7, lexicon).accepted(text, suggestion, context, by_rule=False)`."""

    def __init__(self, min_confidence: float, lexicon: Lexicon) -> None:
        self._min_confidence = min_confidence
        self._lexicon = lexicon

    def accepted(
        self,
        text: str,
        suggestion: ModelSuggestion | None,
        context: SessionContext,
        by_rule: bool,
    ) -> CaseMatch | None:
        """The model's answer as a hint, or None: no hint, incomplete, unsure or off the rules."""
        if suggestion is None or suggestion.decision != "SHOW_HINT":
            return None
        answer = _without_empty_meaning(right_way_round(text, suggestion))
        if answer is None or not answer.reason or self._rejected(text, answer, context, by_rule):
            return None
        language = self._due_language(text, answer, context)
        candidates, open_context = None, None
        if answer.reason in _OPEN_SEARCH_REASONS:
            candidates, open_context = _extra_candidates(answer), text.strip()
        return CaseMatch(
            answer.reason,
            answer.expression or "",
            answer.meaning,
            answer.example,
            language or language_named(answer.expression_language),
            candidates,
            open_context,
        )

    def _due_language(
        self, text: str, answer: ModelSuggestion, context: SessionContext
    ) -> Language | None:
        """The language the hint has to be in; None when the model's own label decides.

        A question that names no language ("Como se diz abacaxi?") is asked in one language for
        a word of the other: there the label decides. A listener who did not understand says so
        in any language ("O quê?"); the word the other person needed is in the language of THEIR
        sentence. An aside in the middle of a sentence ("I need my, como é que fala, ...") leaves
        the sentence's own language.
        """
        before = _last_text(context)
        if answer.reason is Reason.NOT_UNDERSTOOD and before:
            return spoken_language(before, self._lexicon, context.focus)
        if open_ask(text) and not searching_aside(text, context.focus):
            return None
        return context.focus

    def _rejected(
        self, text: str, answer: ModelSuggestion, context: SessionContext, by_rule: bool
    ) -> bool:
        """The checks that keep a wrong or unwanted hint off the screen (DECISIONS D-29)."""
        word, said = answer.expression or "", answer.meaning
        due = self._due_language(text, answer, context)
        if self._doubtful(answer, context.focus, due, by_rule) or made_up(text, answer):
            return True
        if answer.reason is not None and unseen(text, answer.reason, context):
            return True
        if translates_the_question(answer) or already_said(answer, context):
            return True
        # "Molho para salada?": trying out a word they were just given. Not a listener echoing
        # what they did not understand ("The place of the books?"): that is checked by `unseen`.
        if answer.reason is not Reason.NOT_UNDERSTOOD and only_the_word(text, answer, context):
            return True
        return not asks_for_word(text) and only_extends(word, said)

    def _doubtful(
        self, answer: ModelSuggestion, focus: Language, due: Language | None, by_rule: bool
    ) -> bool:
        """The model is not sure itself, or its word is not in the language it has to be in.

        Seen with real sentences: "maybe a ranch?" (English) got the hint "fazenda". Quiet first.
        `due` is that language, None when the model's own label decides (see `_due_language`).
        """
        # No stated confidence is no certainty: quiet first (AGENTS 7.2). Only a word the lexicon
        # rules already found (a false-friend candidate the model is confirming) may go without.
        unsure = (answer.confidence is None and not by_rule) or (
            answer.confidence is not None and answer.confidence < self._min_confidence
        )
        hint_in = language_named(answer.expression_language)
        said_in = language_named(answer.meaning_language)
        wrong_side = due is not None and hint_in is not None and hint_in is not due
        same_side = said_in is focus and answer.reason is Reason.CODE_SWITCH
        return unsure or wrong_side or same_side  # same_side: a synonym, not a translation
