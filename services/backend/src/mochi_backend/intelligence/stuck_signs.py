"""What a sentence looks like when its speaker is stuck and does not say so. No model.

Someone who asks "how do you say X?" is easy to help. Most people do not ask: they stop before the
word, start the sentence again, describe the thing, or mutter "como é que fala" to themselves
(AGENTS 7.1 cases 5-7 and 9). The speech recogniser writes none of that as "…": "It's raining and I
forgot my" simply ends. These signs are what can be seen in the text alone. They are clues for the
hint model, which sees them next to the sentence (`ModelRequest.noticed`), never verdicts: "It's
the place where I grew up." describes a place and nobody is stuck (DECISIONS D-42).
"""

import re
from enum import StrEnum

from mochi_backend.intelligence.tokens import lowered, words_of
from mochi_contracts import Language


class StuckSign(StrEnum):
    """One thing seen in a sentence. The values are the names the hint model is told."""

    STOPS_SHORT = "stops_short"  # ends, or hesitates, where a word should follow: "I forgot my"
    STARTS_OVER = "starts_over"  # "We should, we need to, we have to make it later."
    DESCRIBES = "describes"  # "the place where you buy medicine"
    SEARCHES = "searches"  # "I need my, como é que fala, ..."
    PARTNER_LOST = "partner_lost"  # "Sorry, a what?"


# Words a finished sentence does not end on. Only the safe ones: "I told her.", "Come in." and
# "I don't want to." are complete, so "her", "in" and "to" are not here.
_EN_NEEDS_A_NOUN = "the a an my your our their"
_PT_NEEDS_A_NOUN = (
    "o a os as um uma uns umas meu minha meus minhas seu sua nosso nossa ao à num numa pelo pela"
)
_NEEDS_A_NOUN = {
    Language.EN: frozenset(_EN_NEEDS_A_NOUN.split()),
    Language.PT_BR: frozenset(_PT_NEEDS_A_NOUN.split()),
}
# These also end a question that is complete ("What is it made of?"), so not before a "?".
# English leaves its prepositions at the end ("That's the one I told you about."), so only "of"
# is here; Portuguese never does, so there they all are.
_EN_NEEDS_MORE = "of and or but because than very"
_PT_NEEDS_MORE = "de do da dos das no na em para pra com por e ou mas que porque"
_NEEDS_MORE = {
    Language.EN: frozenset(_EN_NEEDS_MORE.split()),
    Language.PT_BR: frozenset(_PT_NEEDS_MORE.split()),
}
# How a hesitation is written. Not "é": alone it is the verb ("O meu carro é"). And not "um" in
# Portuguese, where it is the article ("Quero só um."): there the sound is written "hum".
_FILLER = {
    Language.EN: r"(?:u+m+|u+h+|h+m+|e+r+|a+h+)",
    Language.PT_BR: r"(?:h+u+m+|h+m+|u+h+|a+h+|h+ã+)",
}
_PAUSE = r"(?:,|…|\.\.\.|—)"


def _tail(language: Language) -> re.Pattern[str]:
    """Punctuation and fillers at the very end, to find the last real word before them."""
    return re.compile(rf"(?:[\s.,…!—-]|\b{_FILLER[language]}\b)+$")


def _written_pause(language: Language) -> re.Pattern[str]:
    """A sentence that ends in "..." or in a filler."""
    return re.compile(rf"(?:…|\.\.\.|\b{_FILLER[language]}\b)[\s.…]*$")


def _hesitation(language: Language) -> re.Pattern[str]:
    """A word, a pause and a filler in the middle of a sentence: "the, hmm, ..."."""
    return re.compile(rf"\b([^\W\d_]+)\s*{_PAUSE}\s*{_FILLER[language]}\b")


_BREAK = re.compile(r"[,.;:!?…—]+|\s-\s")
_MIN_START_WORDS = 2  # "I, I, I can't believe it!" is emphasis, not a restart
_MAX_START_WORDS = 4
_MIN_STARTS = 2  # "I like the, the blue one." has one, and so does every second sentence
# A start that was given up ends on a word that wants more: "We should,", "She is very,", "Eu
# quero,". "I went home, I ate dinner, I watched a film." is three things that happened.
_EN_GIVEN_UP = "to should will would can could must need want have has is are was am very going"
_PT_GIVEN_UP = "quero preciso vou vai tenho posso devo é está muito que de para pra o um uma"
_GIVEN_UP = frozenset(f"{_EN_GIVEN_UP} the a my {_PT_GIVEN_UP}".split())
_GENERIC = (
    r"thing|stuff|place|machine|paper|person|man|woman|guy|doctor|animals?|tool|shop|store|"
    r"coisa|negócio|treco|lugar|máquina|papel|pessoa|homem|mulher|cara|bicho|loja"
)
_DESCRIBING = re.compile(
    rf"\b(?:{_GENERIC})\b[\s,]+(?:\w+[\s,]+){{0,2}}?"
    r"(?:that|where|who|you|they|for|to|of|que|onde|de|para|pra)\b"
)
_SEARCHING = re.compile(
    r"como é que (?:se )?(?:fala|diz|chama)|como (?:é|era) mesmo|como (?:se )?chama|"
    r"qual é (?:a palavra|o nome)|(?:não|nao) lembro (?:a palavra|o nome)|esqueci o nome|"
    r"how (?:do|can|would) (?:you|i) (?:say|call)|how to say|how is it called|"
    r"what(?:'s| is) (?:it|that) called|what(?:'s| is) the (?:name|word)|"
    r"i (?:don'?t|can'?t) remember the (?:word|name)"
)
_WHAT = r"(?:what|qu[eê]|o qu[eê])"
_LOST = re.compile(
    rf"(?:^|[.,!?]\s*)(?:(?:a|an|the|your|my|um|uma|o|a|seu|sua)\s+)?{_WHAT}\s*\?|"
    r"what do you mean|what does (?:that|it) mean|what(?:'s| is) that\b|"
    r"i (?:don'?t|didn'?t|did not) (?:understand|get (?:it|that))|"
    r"como assim|(?:não|nao) entendi|o que é isso"
)
_MAX_ECHO_WORDS = 5


def _last_word(low: str, language: Language) -> str:
    words = words_of(_tail(language).sub("", low))
    return words[-1] if words else ""


def stops_short(text: str, language: Language) -> bool:
    """True when the sentence ends, or hesitates, where a word should follow.

    Example: `stops_short("It's raining and I forgot my", Language.EN)` is True, and so is
    "Can I borrow your, um"; "I forgot my keys." and "Who did you go with?" are not.
    """
    low = lowered(text)
    last = _last_word(low, language)
    asked = low.rstrip().endswith("?")
    if last in _NEEDS_A_NOUN[language] or (last in _NEEDS_MORE[language] and not asked):
        return True
    if _written_pause(language).search(low) and len(words_of(low)) > 1:
        return True
    open_words = _NEEDS_A_NOUN[language] | _NEEDS_MORE[language]
    return any(found.group(1) in open_words for found in _hesitation(language).finditer(low))


def _abandoned(fragment: list[str], following: list[str]) -> bool:
    """A short start, given up on a word that wants more, that the next piece begins again."""
    short = _MIN_START_WORDS <= len(fragment) <= _MAX_START_WORDS
    again = bool(following) and fragment[0] == following[0]
    return short and again and fragment[-1] in _GIVEN_UP


def starts_over(text: str) -> bool:
    """True when the speaker began the sentence two or more times before getting through it.

    Example: `starts_over("We should, we need to, we have to make the meeting later.")` is True;
    "I like the, the blue one." and "I, I, I can't believe it!" are not.
    """
    pieces = [words_of(piece) for piece in _BREAK.split(lowered(text))]
    pieces = [piece for piece in pieces if piece]
    starts = [
        index for index in range(len(pieces) - 1) if _abandoned(pieces[index], pieces[index + 1])
    ]
    if len(starts) < _MIN_STARTS:
        return False
    longest_start = max(len(pieces[index]) for index in starts)
    return len(pieces[starts[-1] + 1]) > longest_start  # a list has pieces of one length


def describes(text: str) -> bool:
    """True when a general word stands in for the thing, with what it does or is for.

    Example: `describes("I went to the place where you buy medicine.")` is True;
    "The thing is, I don't like horror movies." is not.
    """
    return _DESCRIBING.search(lowered(text)) is not None


def searches(text: str) -> bool:
    """True when the speaker looks for the word aloud, often in their own language.

    Example: `searches("It's cold, I need my, como é que fala, my...")` is True.
    """
    return _SEARCHING.search(lowered(text)) is not None


def before_search(text: str) -> str | None:
    """What was said before the speaker began to look for the word aloud; None when they did
    not, or when the search opens the turn.

    Example: `before_search("We need to, como é que fala, destravar isso")` is "we need to, ".
    """
    found = _SEARCHING.search(lowered(text))
    before = lowered(text)[: found.start()] if found else ""
    return before if words_of(before) else None


def search_language(text: str) -> Language | None:
    """The language the speaker looks for the word in. Example: "..., como é que fala, ..." is
    Portuguese, "..., how do you say, ..." English; None when nobody is searching."""
    found = _SEARCHING.search(lowered(text))
    if found is None:
        return None
    portuguese = found.group(0).startswith(("como", "qual", "não", "nao", "esqueci"))
    return Language.PT_BR if portuguese else Language.EN


def searching_aside(text: str, language: Language) -> bool:
    """True when the search is an aside in a sentence that had stopped short before it.

    "Eu preciso do, how do you say, para abrir a porta." asks nothing about "para abrir a
    porta": the word wanted is the one missing after "do". A question that begins the turn
    ("How do you say fork?") is not an aside.
    """
    found = _SEARCHING.search(lowered(text))
    return found is not None and stops_short(lowered(text)[: found.start()], language)


def _echoes(low: str, before: str | None) -> bool:
    """A short question made only of words the other person just said: "The place of the books?"."""
    question = low.split("?", 1)[0]
    words = words_of(question)
    if before is None or "?" not in low or not 1 < len(words) <= _MAX_ECHO_WORDS:
        return False
    said = set(words_of(before))
    return all(word in said for word in words)


def partner_lost(text: str, before: str | None) -> bool:
    """True when the listener shows they did not understand what was just said.

    `before` is the sentence before this one. Example: `partner_lost("Sorry, a what?", None)`
    is True; `partner_lost("The place of the books?", "I went to the place of the books.")` too.
    """
    low = lowered(text)
    return _LOST.search(low) is not None or _echoes(low, before)


def stuck_signs(text: str, before: str | None, language: Language) -> list[StuckSign]:
    """Every sign in `text`, which is in `language`; `before` is the previous sentence, if any.

    Example: `stuck_signs("I forgot my", None, Language.EN)` is `[StuckSign.STOPS_SHORT]`.
    """
    seen = {
        StuckSign.STOPS_SHORT: stops_short(text, language),
        StuckSign.STARTS_OVER: starts_over(text),
        StuckSign.DESCRIBES: describes(text),
        StuckSign.SEARCHES: searches(text),
        StuckSign.PARTNER_LOST: partner_lost(text, before),
    }
    return [sign for sign, found in seen.items() if found]
