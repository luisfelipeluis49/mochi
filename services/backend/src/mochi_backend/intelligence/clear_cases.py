"""Cases 1-3 (code switch, says unknown, asks partner) with rules. Case 4 lives in the flow."""

import re

from mochi_backend.intelligence.hint_builder import CaseMatch, match_from_entry
from mochi_backend.intelligence.language_guess import is_mostly
from mochi_backend.intelligence.lexicon import Lexicon, LexiconEntry, other_language
from mochi_backend.intelligence.tokens import lowered, normalized
from mochi_contracts import Language, Reason, SessionContext

ASK_PATTERN = re.compile(
    r"how do you say|how do i say|what(?:'s| is) the word for|what do you call|"
    r"i don'?t know (?:the word|how to say)|i can'?t remember the word|"
    r"como (?:se )?(?:diz|fala)|qual (?:é )?a palavra"
)


_ASKED = re.compile(
    r"(?:how do (?:you|i) say|what(?:'s| is) the word for|what do you call|"
    r"como (?:se )?(?:diz|fala)|qual (?:é )?a palavra (?:para|pra|de))(?P<term>[^?.!]*)"
)
# "in English", "em português", also with a hesitation in between: "in, uh— Portuguese"
_NAMED_LANGUAGE = re.compile(
    r"\b(?:in|em)\b(?:[\s,…—-]|\b(?:uh+|um+|er+|like|tipo)\b)*"
    r"(?:english|portuguese|ingl[eê]s|portugu[eê]s)\b.*$"
)
_LEAD_IN = re.compile(r"^(?:[\s,:;…\"'“”‘’-]|\b(?:like|uh+|um+|er+|tipo)\b)+")


_WANTS_ENGLISH = re.compile(r"\b(?:in|em)\b[^?.!]{0,12}\b(?:english|ingl[eê]s)\b")
_WANTS_PORTUGUESE = re.compile(r"\b(?:in|em)\b[^?.!]{0,12}\bportugu[eê]s[e]?\b")


def wanted_language(text: str) -> Language | None:
    """The language a question asks for by name. Example: "...carteira em inglês?" -> English."""
    low = lowered(text)
    if _WANTS_ENGLISH.search(low):
        return Language.EN
    return Language.PT_BR if _WANTS_PORTUGUESE.search(low) else None


def asks_for_word(text: str) -> bool:
    """True when the turn asks how to say something. Example: "How do you say fila?" -> True."""
    return ASK_PATTERN.search(lowered(text)) is not None


def asked_term(text: str) -> str | None:
    """The word or description a question asks about, when the question names it.

    Seen live: `I will have to adiar our meeting. How do I say "garfo" in English?` asks about
    "garfo", not about the other foreign word in the turn. None when nothing follows the question
    ("Como se fala..."), so the caller looks at the whole turn as before.
    """
    # a pause is written as "..." or "…"; the last question in the turn is the one being asked
    asks = list(_ASKED.finditer(lowered(text).replace("...", " ").replace("…", " ")))
    if not asks:
        return None
    term = _LEAD_IN.sub("", _NAMED_LANGUAGE.sub("", asks[-1].group("term")))
    term = term.strip(" \"'“”‘’,:;-")
    return None if not term or ASK_PATTERN.search(term) else term


def unfinished_question(text: str) -> bool:
    """True for a question that stops before naming its word. Example: "Como se fala..." -> True."""
    return asks_for_word(text) and asked_term(text) is None


def _addressed_partner(text: str, context: SessionContext) -> bool:
    names = "|".join(p.user_id for p in context.participants)
    return re.match(rf"\s*(?:{names})\b[,\s]", lowered(text)) is not None


def find_entry(text: str, context: SessionContext, lexicon: Lexicon) -> LexiconEntry | None:
    """The lexicon word being asked about: a foreign word, else a described cue.

    Only what the question names is searched when it names something (`asked_term`).
    """
    asked = asked_term(text) or text
    words = lexicon.entries_with_word(normalized(asked), other_language(context.focus))
    return words[0] if words else lexicon.entry_for_cues(lowered(asked))


def mochi_entry(text: str, context: SessionContext, lexicon: Lexicon) -> LexiconEntry | None:
    """The word someone asks Mochi about: a foreign word, or a description after an explicit ask.

    "Oi Mochi, it's raining outside" describes nothing being asked, so it finds no entry.
    """
    asked = (asked_term(text) or text) if asks_for_word(text) else text
    foreign = lexicon.entries_with_word(normalized(asked), other_language(context.focus))
    if foreign:
        return foreign[0]
    return lexicon.entry_for_cues(asked) if asks_for_word(text) else None


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
