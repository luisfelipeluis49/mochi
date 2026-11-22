"""What a real meeting on the device showed on 2026-11-22 (DECISIONS D-69), sentence by sentence
as the recogniser wrote them."""

import pytest

from mochi_backend.intelligence.aloud import wants_to_hear
from mochi_backend.intelligence.clear_cases import asked_term, asks_for_word
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.spoken_focus import focus_for
from mochi_contracts import Language

LEXICON = Lexicon.load()


@pytest.mark.parametrize(
    "said",
    [
        "I'll say it again: can you send me the plan before lunch?",  # Mochi said "umbrella"
        "I'll say it again:.",
        "No, I'm going to say it again. Esse projeto—",
        "Let me say it again.",
        "I have to say it again.",
        "Do you want me to say it again?",
        "Vou falar de novo.",
        "Tenho que falar de novo.",
        "Ele vai falar de novo com o cliente.",
        "Deixa eu repetir a palavra.",
    ],
)
def test_someone_who_will_repeat_themselves_is_not_asking_to_hear_the_hint(said: str) -> None:
    assert not wants_to_hear(said)


@pytest.mark.parametrize(
    "said",
    [
        "Can you say it again?",
        "Say the word again, please.",
        "Fala de novo?",
        "Pode repetir isso?",
        "How do I say it? Can you pronounce it?",
        "Can you say it again so I can say it?",
        "Eu falo errado, pode pronunciar?",
        "Posso repetir? Fala de novo pra mim.",
    ],
)
def test_asking_to_hear_it_again_still_is(said: str) -> None:
    assert wants_to_hear(said)


@pytest.mark.parametrize(
    ("said", "language"),
    [
        # mostly Portuguese words, and an English sentence: its hint has to be English
        ('Okay, good. We need to— Como é que fala "destravar a autenticação"?', Language.EN),
        ("Because we need to, como é que fala, destravar a autenticação.", Language.EN),
        ("Eu preciso do, how do you say, para abrir a porta.", Language.PT_BR),
        ("We need to, como e que fala, destravar a autenticacao?", Language.EN),  # no accents
        # nothing was begun in the other language: the older rules decide
        ("Ben, como se diz recibo?", Language.EN),
        ("Eu não sei, how do you say recibo?", Language.EN),  # an aside in their own language
        ("Eu não lembro, how do you say guarda-chuva in English?", Language.EN),
        ("E aí Mochi, what's the word for fila?", Language.EN),
    ],
)
def test_a_sentence_left_to_ask_for_its_word_keeps_the_language_it_began_in(
    said: str, language: Language
) -> None:
    assert focus_for(said, LEXICON, Language.EN) is language


def test_como_e_que_fala_asks_for_a_word_like_como_se_diz() -> None:
    said = "Como é que fala destravar a autenticação?"
    assert asks_for_word(said) and asked_term(said) == "destravar a autenticação"


def test_two_explanations_may_follow_each_other_as_soon_as_a_card_is_gone() -> None:
    # "piece of cake" 17 s after "circle back" got nothing: the pause was 20 s
    assert IntelligenceSettings().explain_gap_seconds == IntelligenceSettings().hint_ttl_seconds


@pytest.mark.parametrize(
    "story",
    [
        "Não sei como é que diz pra ele que a reunião atrasou.",
        "Você sabe como é que fala com o fornecedor sobre o recibo?",
        "Depende de como é que fala na reunião.",
    ],
)
def test_telling_how_something_is_said_is_not_asking_for_a_word(story: str) -> None:
    assert not asks_for_word(story)
