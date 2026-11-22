"""Which language a turn is practising (AGENTS 7.3), decided per sentence.

Two people share one mic and each speaks their own language, so one session focus is not enough.
"""

from mochi_backend.intelligence.clear_cases import asked_term, asks_for_word, wanted_language
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.stuck_signs import before_search, search_language
from mochi_backend.intelligence.tokens import normalized, words_of
from mochi_backend.intelligence.wake_phrase import says_mochi
from mochi_contracts import Language


def _asked_language(text: str, lexicon: Lexicon) -> Language | None:
    """The language of the lexicon word being asked about, when only one language appears."""
    words = normalized(asked_term(text) or text)
    english = bool(lexicon.entries_with_word(words, Language.EN))
    portuguese = bool(lexicon.entries_with_word(words, Language.PT_BR))
    if english == portuguese:
        return None
    return Language.EN if english else Language.PT_BR


_MIN_BEGUN = 3  # "we need to", "eu preciso do": fewer words are a name or a greeting


def _begun_in(text: str, lexicon: Lexicon, fallback: Language) -> Language | None:
    """The language of a sentence its speaker left to ask, in the other one, for the next word.

    Seen live (D-69): "We need to, como é que fala, destravar a autenticação?" is mostly
    Portuguese words, and is an English sentence: the speaker broke off to ask in their own
    language. Counted as Portuguese, the English hint was dropped.
    Example: that sentence -> English; "Ben, como se diz recibo?" -> None (nothing was begun);
    "Ana, eu não sei, como se diz recibo?" -> None (asked in the language it was begun in).
    """
    before = before_search(text)
    if before is None or len(words_of(before)) < _MIN_BEGUN or says_mochi(before):
        return None  # "E aí Mochi, what's the word for fila?" begins nothing: it calls Mochi
    language = spoken_language(before, lexicon, fallback)
    return language if search_language(text) is other_language(language) else None


def focus_for(text: str, lexicon: Lexicon, fallback: Language) -> Language:
    """The language the speaker is practising in this turn.

    A question is asked in the speaker's own language about a word in the other one, so the
    practised language is the opposite of the asked word: "Ben, como se diz recibo?" (a
    Portuguese word) practises English. Any other sentence practises the language it is mostly in:
    "Eu esqueci meu umbrella" practises Portuguese. A tie or no evidence gives `fallback`.
    A sentence left unfinished to look for its word practises the language it was begun in.
    """
    begun = _begun_in(text, lexicon, fallback)
    if begun is not None:
        return begun
    if asks_for_word(text):
        named = wanted_language(text)  # "... em inglês?" says it outright
        if named is not None:
            return named
        asked = _asked_language(text, lexicon)
        if asked is not None:
            return other_language(asked)
    return spoken_language(text, lexicon, fallback)
