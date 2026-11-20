"""Cases 1-3 (code switch, says unknown, asks partner) with rules. Case 4 lives in the flow."""

import re

from mochi_backend.intelligence.hint_builder import CaseMatch, match_from_entry
from mochi_backend.intelligence.language_guess import ENGLISH_WORDS, PORTUGUESE_WORDS, is_mostly
from mochi_backend.intelligence.lexicon import Lexicon, LexiconEntry, other_language
from mochi_backend.intelligence.tokens import lowered, normalized, words_of
from mochi_contracts import Language, Reason, SessionContext

ASK_PATTERN = re.compile(
    r"how do you say|how do i say|what(?:'s| is) the word for|what do you call|"
    r"i don'?t know (?:the word|how to say)|i can'?t remember the word|i forgot the word|"
    r"como (?:se )?(?:diz|fala)|qual (?:é )?a palavra|esqueci a palavra"
)
# "Limpar em inglês?": a word and the language wanted, and nothing else in that sentence
_SHORT_ASK = re.compile(
    r"(?:^|[.!?…]\s*)(?P<term>[^.!?…]+?)\s+(?:in|em)\s+"
    r"(?P<language>english|portuguese|ingl[eê]s|portugu[eê]s)\s*\?"
)
_MAX_SHORT_ASK_WORDS = 3


_ASKED = re.compile(
    r"how do (?:you|i) say|what(?:'s| is) the word for|what do you call|"
    r"i don'?t know (?:the word(?: for)?|how to say)|"
    r"i (?:can'?t remember|forgot) the word(?: for)?|"
    r"como (?:se )?(?:diz|fala)|qual (?:é )?a palavra (?:para|pra|de)|"
    r"esqueci a palavra(?: para| pra| de)?"
)
# "How do you say that?" points at a word said elsewhere: it names nothing itself
_POINTING = frozenset(
    {"that", "it", "this", "isso", "isto", "aquilo", "esse", "essa", "este", "esta"}
)
_ARTICLES = frozenset({"the", "a", "an", "o", "os", "as", "um", "uma"})
# "Can we talk in English?", "Tudo em inglês?": about the talk itself, not about a word
_TALK_WORDS_EN = "speak talk say answer write switch continue practice practise let s t"
_TALK_WORDS_MORE = "everything only again always better easier"
_TALK_WORDS_PT = "responder continuar praticar escrever dizer conversar melhor"
_ABOUT_THE_TALK = frozenset(f"{_TALK_WORDS_EN} {_TALK_WORDS_MORE} {_TALK_WORDS_PT}".split())
_TO_SENTENCE_END = re.compile(r"[^?.!]*")
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


def _flat(text: str) -> str:
    """Lowercase, with a written pause ("..." or "…") turned into a space."""
    return lowered(text).replace("...", " ").replace("…", " ")


def _short_ask(low: str) -> str | None:
    """The word in "Limpar em inglês?" or "The key... in Portuguese?", else None.

    Only a bare word or a short name of a thing counts. A clause in either language does not:
    "Was the meeting in Portuguese?", "A reunião foi em inglês?" and "Can we talk in English?"
    ask for no word.
    """
    found = _SHORT_ASK.search(low)
    if found is None:
        return None
    words = words_of(_LEAD_IN.sub("", found.group("term")))
    if len(words) > 1 and words[0] in _ARTICLES:
        words = words[1:]
    plain = ENGLISH_WORDS | PORTUGUESE_WORDS | _ABOUT_THE_TALK
    if not words or len(words) > _MAX_SHORT_ASK_WORDS or any(w in plain for w in words):
        return None
    return " ".join(words)


def asks_for_word(text: str) -> bool:
    """True when the turn asks how to say something. Example: "How do you say fila?" -> True."""
    low = _flat(text)
    return ASK_PATTERN.search(low) is not None or _short_ask(low) is not None


def _named_after_ask(low: str) -> str:
    """What follows the last "how do you say" in the turn, without the language it names."""
    asks = list(_ASKED.finditer(low))
    if not asks:  # the last one: "Como se fala... como se fala carteira?" asks about carteira
        return ""
    rest = _TO_SENTENCE_END.match(low, asks[-1].end())
    term = _NAMED_LANGUAGE.sub("", rest.group(0) if rest else "")
    term = _LEAD_IN.sub("", term).strip(" \"'“”‘’,:;-")
    return "" if term in _POINTING else term


def asked_term(text: str) -> str | None:
    """The word or description a question asks about, when the question names it.

    Seen live: `I will have to adiar our meeting. How do I say "garfo" in English?` asks about
    "garfo", not about the other foreign word in the turn. None when nothing follows the question
    ("Como se fala..."), so the caller looks at the whole turn as before.
    """
    low = _flat(text)
    term = _named_after_ask(low) or _short_ask(low) or ""
    return None if not term or ASK_PATTERN.search(term) else term


_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")


def question_itself(text: str) -> str:
    """Only the sentence that asks, when the turn holds more; the whole turn otherwise.

    Seen with a real model: given `...adiar our meeting. How do I say "garfo" in English?` it
    answered for "adiar". What is not sent cannot distract.
    """
    sentences = [s.strip() for s in _SENTENCE.findall(text.replace("...", "…"))]
    asking = [s for s in sentences if asked_term(s)]
    return asking[-1] if asking else text


def unfinished_question(text: str) -> bool:
    """True for a question that stops before naming its word. Example: "Como se fala..." -> True."""
    return asks_for_word(text) and asked_term(text) is None


def addressed_partner(text: str, context: SessionContext) -> bool:
    """True when the turn opens with a participant's name. Example: "Ben, como se diz...?"."""
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
    reason = Reason.ASKS_PARTNER if addressed_partner(text, context) else Reason.SAYS_UNKNOWN
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
