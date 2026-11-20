"""Checks on what the hint model answered: what keeps a wrong or unwanted hint off the screen.

Each one comes from a mistake seen with a real model on real speech (DECISIONS D-29).
"""

from mochi_backend.intelligence.clear_cases import asks_for_word, wanted_language
from mochi_backend.intelligence.hint_builder import CaseMatch
from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.tokens import folded, has_phrase, normalized, words_of
from mochi_contracts import Language, Reason, SessionContext

_STEM_LETTERS = 3  # "adi" joins "adiar" and "adiei"; longer would miss the verb forms


def needed_word(text: str, expression: str, meaning: str | None) -> tuple[str | None, str | None]:
    """A hint must be the word the person NEEDED. A model sometimes returns the word they said.

    Then the two fields are the wrong way round ("garfo" / "fork" for "pass me the garfo"):
    swap them. With nothing to swap in, there is no hint.
    Example: `needed_word("pass me the garfo", "garfo", "fork")` is `("fork", "garfo")`.
    """
    said = normalized(text)
    if not has_phrase(said, expression):
        return expression, meaning
    if meaning and not has_phrase(said, meaning):
        return meaning, expression
    return None, None


def same_words(one: str, other: str) -> bool:
    """Example: `same_words("Fork", "fork ")` -> True."""
    return normalized(one) == normalized(other)


def language_named(label: str | None) -> Language | None:
    """The language a model's label means. Example: "en-US", "English", "EN" -> English."""
    low = (label or "").strip().lower()
    if low.startswith(("en", "ing")):
        return Language.EN
    return Language.PT_BR if low.startswith(("pt", "por")) else None


def open_ask(text: str) -> bool:
    """A question about a word that does not say which language it wants the word in."""
    return asks_for_word(text) and wanted_language(text) is None


def in_its_language(context: SessionContext, match: CaseMatch) -> SessionContext:
    """The context a hint is built in: the match's own language when it carries one."""
    if match.language is None or match.language is context.focus:
        return context
    return context.model_copy(update={"focus": match.language})


def right_way_round(text: str, answer: ModelSuggestion) -> ModelSuggestion | None:
    """The answer with `expression` as the word needed; None when there is nothing to show.

    A model sometimes returns the two words swapped (see `needed_word`); then their language
    labels are swapped back with them.
    """
    if not answer.expression:
        return None
    expression, meaning = needed_word(text, answer.expression, answer.meaning)
    if expression is None or expression == answer.expression:
        return answer if expression else None
    labels = {
        "expression_language": answer.meaning_language,
        "meaning_language": answer.expression_language,
    }
    return answer.model_copy(update={"expression": expression, "meaning": meaning, **labels})


def _stems(phrase: str) -> set[str]:
    """How each word starts, without accents: enough to match "garfo" with "garfos"."""
    return {folded(word)[:_STEM_LETTERS] for word in words_of(phrase)}


def made_up(text: str, answer: ModelSuggestion) -> bool:
    """A code switch names a word of the other language: it has to be in the sentence.

    Seen with a real model: "pass me the bathroom" got "toilet", for a "banheiro" nobody said.
    Word beginnings are compared, so "garfos" and "adiei" still count for "garfo" and "adiar".
    """
    if answer.reason is not Reason.CODE_SWITCH or not answer.meaning:
        return False
    return not (_stems(answer.meaning) & _stems(text))


def only_the_word(text: str, answer: ModelSuggestion, context: SessionContext) -> bool:
    """True when the whole turn is a word that was already in the air, and no question about it.

    Someone who says only "Molho para salada?" right after being given it is trying the word
    out or checking it, not stuck. A word nobody mentioned before ("Dor de cabeça...") is.
    """
    words = [w for w in (answer.expression, answer.meaning) if w]
    if asks_for_word(text) or normalized(text) not in {normalized(w) for w in words}:
        return False
    earlier = [normalized(t.text) for t in context.recent_turns]
    earlier += [normalized(h.expression) for h in context.recent_hints]
    return any(has_phrase(before, word) for before in earlier for word in words)


def only_extends(expression: str, meaning: str | None) -> bool:
    """A "hint" that just adds to the word they said is an invention, not a translation.

    Seen with a real sentence: "pass me the bathroom" got "bathroom key" for "bathroom".
    """
    if not meaning:
        return False
    return has_phrase(normalized(expression), meaning) or has_phrase(
        normalized(meaning), expression
    )
