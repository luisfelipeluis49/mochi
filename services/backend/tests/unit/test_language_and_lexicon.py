"""Lexicon lookups, language guess, wake phrase, owner."""

import pytest

from mochi_backend.intelligence.language_guess import (
    count_by_language,
    has_foreign_word,
    is_mostly,
    strip_proper_nouns,
)
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.tokens import has_phrase, normalized, words_of
from mochi_backend.intelligence.wake_phrase import has_wake_phrase, without_wake_phrase
from mochi_backend.intelligence.word_owner import owner_for
from mochi_contracts import Language
from tests.factories import ANA, BEN, make_context

LEXICON = Lexicon.load()


def test_words_split_on_hyphens_and_normalize() -> None:
    assert words_of("Guarda-chuva!") == ["guarda", "chuva"]
    assert normalized("Guarda-chuva!") == "guarda chuva"


def test_has_phrase_matches_whole_words_only() -> None:
    assert has_phrase("i forgot my guarda chuva", "guarda-chuva")
    assert not has_phrase("the filar", "fila")


def test_phrases_match_with_or_without_accents_because_speech_to_text_drops_them() -> None:
    assert has_phrase(normalized("a reuniao começa"), "reunião")
    assert has_phrase(normalized("Eu comi pao de queijo"), "pão de queijo")
    assert Lexicon.load().is_deliberate(normalized("we had pao de queijo"))
    assert not has_phrase(normalized("a reuniao começa"), "reuniões")


def test_lexicon_covers_the_demo_words() -> None:
    expected = {
        "adiar": "postpone",
        "guarda-chuva": "umbrella",
        "recibo": "receipt",
        "fila": "queue",
    }
    found = {e.pt: e.en for e in LEXICON.entries}
    assert expected.items() <= found.items()


def test_entry_for_expression_finds_either_language() -> None:
    assert LEXICON.entry_for_expression("Umbrella") is LEXICON.entry_for_expression("guarda-chuva")


def test_entry_for_cues_and_false_friend() -> None:
    entry = LEXICON.entry_for_cues("the thing for the rain")
    friend = LEXICON.false_friend_in("i pretend to travel")
    assert entry is not None and entry.en == "umbrella"
    assert friend is not None and friend.intended == "intend"
    assert LEXICON.false_friend_in("they pretend to be pirates") is None


def test_other_language() -> None:
    assert other_language(Language.EN) is Language.PT_BR
    assert other_language(Language.PT_BR) is Language.EN


def test_language_counts_and_majority() -> None:
    counts = count_by_language("I need to adiar my meeting", LEXICON)
    assert counts[Language.EN] > counts[Language.PT_BR] >= 1
    assert is_mostly("Eu preciso adiar a reunião amanhã", LEXICON, Language.PT_BR)


def test_proper_nouns_are_not_foreign_words() -> None:
    assert strip_proper_nouns("I like São Paulo").strip() == "I like"
    assert not has_foreign_word("I visited São Paulo last week", LEXICON, Language.EN)
    assert has_foreign_word("I need to adiar it", LEXICON, Language.EN)


@pytest.mark.parametrize(
    "said", ["Oi Mochi, hi", "hi Moshi", "Hey Mochie", "hello Motchi", "ei Moxi"]
)
def test_wake_phrase_is_matched_loosely(said: str) -> None:
    assert has_wake_phrase(said)


@pytest.mark.parametrize("said", ["I love mochi", "Mochi is nice", "oi, tudo bem?"])
def test_wake_phrase_needs_greeting_and_name(said: str) -> None:
    assert not has_wake_phrase(said)


def test_without_wake_phrase_keeps_the_question() -> None:
    assert "what's the word" in without_wake_phrase("Oi Mochi, what's the word for fila?")


def test_owner_is_the_single_learner_of_the_focus_language() -> None:
    assert owner_for(make_context()) == "ana"


def test_owner_is_none_when_rule_does_not_apply() -> None:
    both = BEN.model_copy(update={"target_language": Language.EN})
    assert owner_for(make_context(participants=[ANA, both])) is None
    assert (
        owner_for(make_context(participants=[BEN, BEN.model_copy(update={"user_id": "x"})])) is None
    )
