"""Which language a turn is practising (AGENTS 7.3), decided per sentence.

Two people share one mic and each speaks their own language, so one session focus is not enough.
"""

from mochi_backend.intelligence.clear_cases import asks_for_word
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.tokens import normalized
from mochi_contracts import Language


def _asked_language(text: str, lexicon: Lexicon) -> Language | None:
    """The language of the lexicon word being asked about, when only one language appears."""
    words = normalized(text)
    english = bool(lexicon.entries_with_word(words, Language.EN))
    portuguese = bool(lexicon.entries_with_word(words, Language.PT_BR))
    if english == portuguese:
        return None
    return Language.EN if english else Language.PT_BR


def focus_for(text: str, lexicon: Lexicon, fallback: Language) -> Language:
    """The language the speaker is practising in this turn.

    A question is asked in the speaker's own language about a word in the other one, so the
    practised language is the opposite of the asked word: "Ben, como se diz recibo?" (a
    Portuguese word) practises English. Any other sentence practises the language it is mostly in:
    "Eu esqueci meu umbrella" practises Portuguese. A tie or no evidence gives `fallback`.
    """
    if asks_for_word(text):
        asked = _asked_language(text, lexicon)
        if asked is not None:
            return other_language(asked)
    return spoken_language(text, lexicon, fallback)
