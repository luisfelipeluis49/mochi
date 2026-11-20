"""Cheap language guess per sentence: function-word lists, diacritics, lexicon. No ML."""

import re

from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.tokens import normalized, words_of
from mochi_contracts import Language

# Words that exist in only one language (no "a", "no", "as", "me", "do": they exist in both; and
# no "um": spoken English is full of it as a filler, and it made English turns look Portuguese).
_ENGLISH = (
    "i you he she we they it the an to of and is are was were my your his her our their need "
    "forgot at in on with for this that these those what how does did have has had can will "
    "would should could tomorrow today last week said like be been am not but or so if then "
    "there here when where why who which because about from by "
    "know think good very just really maybe never yes yeah okay ok well now want went go going "
    "get got please thanks thank some any more much many little one two right sure sorry "
    "don't i'm it's that's didn't can't doesn't isn't i'll we're you're let's "
    "day time thing people friend home work food question mean say tell see look"
)
ENGLISH_WORDS = frozenset(_ENGLISH.split())
_PORTUGUESE = (
    "o os uma de da dos das em na nas para pra com sem que e eu você voce ele ela nós "
    "eles elas meu minha seu sua não nao sim como se diz por mais muito está isso aqui "
    "preciso quero vamos hoje ontem onde quando qual obrigado obrigada tudo bem estou "
    "é tá tô né então também já só bom boa agora acho gosto fui foi vai vou ter tem tenho "
    "pode posso fazer coisa casa dia pro num numa até aí lá sobre porque mas ou gente "
    "esqueci palavra falar fala inglês português amigo comida pergunta coisas"
)
PORTUGUESE_WORDS = frozenset(_PORTUGUESE.split())
_ACCENTED = re.compile(r"[ãõçáàéíóúâêô]")
# Capitalised word in the middle of a sentence: a name or place, not a stuck word.
# The pronoun "I" and its contractions ("I'm") are capitalised everywhere, so they are not names.
# The first word of a sentence is capitalised too: only a capital that follows a word counts.
_PROPER_NOUN = re.compile(r"(?<=[^\s.!?…:;\"“”]\s)(?!I\b)[A-ZÀ-Ý][\wÀ-ÿ]*")


def strip_proper_nouns(text: str) -> str:
    """Remove mid-sentence capitalised words. Example: "I like São Paulo" -> "I like ."."""
    return _PROPER_NOUN.sub("", text)


def _word_language(word: str) -> Language | None:
    if word in PORTUGUESE_WORDS or _ACCENTED.search(word):
        return Language.PT_BR
    if word in ENGLISH_WORDS:
        return Language.EN
    return None


def count_by_language(text: str, lexicon: Lexicon) -> dict[Language, int]:
    """Words per language. Example: "I need to adiar my meeting" -> EN 4, PT_BR 1."""
    counts = {Language.EN: 0, Language.PT_BR: 0}
    for word in words_of(text):
        found = _word_language(word)
        if found is not None:
            counts[found] += 1
    for language in counts:
        counts[language] += len(lexicon.entries_with_word(normalized(text), language))
    return counts


def spoken_language(text: str, lexicon: Lexicon, fallback: Language) -> Language:
    """The language most of the sentence is in; a tie or no evidence gives `fallback`.

    Two people share one mic and each speaks their own language, so the language is decided
    per turn, not once per session. Example: "Eu esqueci meu umbrella" -> pt-BR.
    """
    counts = count_by_language(strip_proper_nouns(text), lexicon)
    if counts[Language.EN] == counts[Language.PT_BR]:
        return fallback
    return Language.EN if counts[Language.EN] > counts[Language.PT_BR] else Language.PT_BR


def is_mostly(text: str, lexicon: Lexicon, language: Language) -> bool:
    """True when `language` has strictly more evidence than the other language."""
    counts = count_by_language(text, lexicon)
    return counts[language] > counts[other_language(language)]


def has_foreign_word(text: str, lexicon: Lexicon, focus: Language) -> bool:
    """True when the text (minus names) contains a word of the non-focus language."""
    counts = count_by_language(strip_proper_nouns(text), lexicon)
    return counts[other_language(focus)] > 0
