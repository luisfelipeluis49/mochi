"""Cases 5-9 fast path: markers plus lexicon cues. Unresolved markers go to the model."""

import re

from mochi_backend.intelligence.clear_cases import find_entry
from mochi_backend.intelligence.hint_builder import CaseMatch, match_from_entry
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import Suspect
from mochi_backend.intelligence.tokens import has_phrase, lowered, normalized
from mochi_contracts import Language, Reason, SessionContext

_TRAILING = re.compile(r"(?:…|\.\.\.|\b(?:um+|uh+|hmm+|er+)\b)[\s.…]*$")
_ELLIPSIS = re.compile(r"…|\.\.\.")
RESTART_ELLIPSES = 2  # "We should… we need to… ...": two or more fragments
_NOT_UNDERSTOOD = re.compile(
    r"what do you mean|sorry, what|i don'?t understand|i did not understand|não entendi|como assim"
)
# A description instead of the word: "the thing for...", "the paper they give you when you pay".
_DESCRIBING = re.compile(
    r"\b(?:the|a) (?:thing|paper|stuff|object|tool|item|bag|place)\b|\bwhen you\b|\bthey give\b"
)


def marker_for(text: str) -> Reason | None:
    """The hesitation marker in a turn, if any.

    "We should… we need to… make it later." -> restarts (two fragments, then the sentence goes on);
    "It's raining and I forgot my… um…" -> trails_off (it ends in a pause).
    """
    low = lowered(text)
    if _NOT_UNDERSTOOD.search(low):
        return Reason.NOT_UNDERSTOOD
    if len(_ELLIPSIS.findall(low)) >= RESTART_ELLIPSES and not _TRAILING.search(low):
        return Reason.RESTARTS
    return Reason.TRAILS_OFF if _TRAILING.search(low) else None


def _look_alike(text: str, lexicon: Lexicon, focus: Language) -> CaseMatch | None:
    friend = lexicon.false_friend_in(lowered(text), focus)
    if friend is None:
        return None
    return CaseMatch(Reason.LOOK_ALIKE, friend.intended, friend.meaning, friend.example)


def suspect_in(text: str, lexicon: Lexicon, focus: Language) -> Suspect | None:
    """The false friend the lexicon finds in a sentence, as the hint model is told about it.

    Example: "I pretend to travel in July." -> used "pretend", meant "intend", look-alike
    "pretender". None when the lexicon knows no false friend in the sentence.
    """
    friend = lexicon.false_friend_in(lowered(text), focus)
    if friend is None:
        return None
    return Suspect(used=friend.used, meant=friend.intended, look_alike=friend.meaning)


def _from_history(
    history: list[str], context: SessionContext, lexicon: Lexicon
) -> CaseMatch | None:
    for earlier in reversed(history[-2:]):
        entry = find_entry(earlier, context, lexicon)
        if entry is not None:
            return match_from_entry(entry, Reason.NOT_UNDERSTOOD, context)
    return None


def _from_cues(
    text: str, reason: Reason, context: SessionContext, lexicon: Lexicon
) -> CaseMatch | None:
    entry = lexicon.entry_for_cues(lowered(text))
    if entry is None or has_phrase(normalized(text), entry.word(context.focus)):
        # "When you pay, they always give you a receipt." has the cues and the word: not stuck
        return None
    return match_from_entry(entry, reason, context)


def detect_subtle(
    text: str, history: list[str], context: SessionContext, lexicon: Lexicon
) -> CaseMatch | None:
    """Cases 5-9 resolved from the lexicon alone, or None.

    Example: "It's raining and I forgot my… um…" -> trails_off, expression "umbrella".
    """
    reason = marker_for(text)
    if reason is Reason.NOT_UNDERSTOOD:
        return _from_history(history, context, lexicon)
    if reason is not None:
        return _from_cues(text, reason, context, lexicon)
    if _DESCRIBING.search(lowered(text)):
        return _from_cues(text, Reason.TALKS_AROUND, context, lexicon)
    return _look_alike(text, lexicon, context.focus)
