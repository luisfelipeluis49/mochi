"""Cases 1-3 (code switch, says unknown, asks partner) with rules. Case 4 lives in the flow."""

import re

from mochi_backend.intelligence.hint_builder import CaseMatch, match_from_entry
from mochi_backend.intelligence.language_guess import is_mostly
from mochi_backend.intelligence.lexicon import Lexicon, LexiconEntry, other_language
from mochi_backend.intelligence.tokens import lowered, normalized
from mochi_contracts import Reason, SessionContext

ASK_PATTERN = re.compile(
    r"how do you say|how do i say|what(?:'s| is) the word for|what do you call|"
    r"i don'?t know (?:the word|how to say)|i can'?t remember the word|"
    r"como (?:se )?(?:diz|fala)|qual (?:é )?a palavra"
)


def asks_for_word(text: str) -> bool:
    """True when the turn asks how to say something. Example: "How do you say fila?" -> True."""
    return ASK_PATTERN.search(lowered(text)) is not None


def _addressed_partner(text: str, context: SessionContext) -> bool:
    names = "|".join(p.user_id for p in context.participants)
    return re.match(rf"\s*(?:{names})\b[,\s]", lowered(text)) is not None


def find_entry(text: str, context: SessionContext, lexicon: Lexicon) -> LexiconEntry | None:
    """The lexicon word being asked about: a foreign word in the text, else a described cue."""
    foreign = other_language(context.focus)
    words = lexicon.entries_with_word(normalized(text), foreign)
    return words[0] if words else lexicon.entry_for_cues(lowered(text))


def mochi_entry(text: str, context: SessionContext, lexicon: Lexicon) -> LexiconEntry | None:
    """The word someone asks Mochi about: a foreign word, or a description after an explicit ask.

    "Oi Mochi, it's raining outside" describes nothing being asked, so it finds no entry.
    """
    foreign = lexicon.entries_with_word(normalized(text), other_language(context.focus))
    if foreign:
        return foreign[0]
    return lexicon.entry_for_cues(text) if asks_for_word(text) else None


def _asked_match(text: str, context: SessionContext, lexicon: Lexicon) -> CaseMatch | None:
    entry = find_entry(text, context, lexicon)
    if entry is None:
        return None
    reason = Reason.ASKS_PARTNER if _addressed_partner(text, context) else Reason.SAYS_UNKNOWN
    return match_from_entry(entry, reason, context)


def _code_switch_match(text: str, context: SessionContext, lexicon: Lexicon) -> CaseMatch | None:
    if not is_mostly(text, lexicon, context.focus):
        return None  # whole sentence in the other language: nobody is stuck
    foreign = lexicon.entries_with_word(normalized(text), other_language(context.focus))
    return match_from_entry(foreign[0], Reason.CODE_SWITCH, context) if foreign else None


def detect_clear(text: str, context: SessionContext, lexicon: Lexicon) -> CaseMatch | None:
    """Cases 1-3 for one turn, or None.

    Example: "I need to adiar my meeting" with focus "en" -> code_switch, expression "postpone".
    """
    if asks_for_word(text):
        return _asked_match(text, context, lexicon)
    return _code_switch_match(text, context, lexicon)
