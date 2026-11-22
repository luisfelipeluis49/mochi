"""What a real meeting on the device showed on 2026-11-22 (DECISIONS D-69), sentence by sentence
as the recogniser wrote them."""

import pytest

from mochi_backend.intelligence.aloud import wants_to_hear
from mochi_backend.intelligence.clear_cases import (
    asked_term,
    asks_directly,
    asks_for_word,
    question_itself,
)
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


# --- the second real meeting, the same day (DECISIONS D-70)


def test_the_language_named_first_and_the_words_after_it() -> None:
    quoted = 'Hum, how do I say in Portuguese, uh, "I will finish my work tomorrow"?'
    assert asked_term(quoted) == "i will finish my work tomorrow"
    assert asked_term("Como se diz em inglês, tipo, guarda-chuva?") == "guarda-chuva"
    assert asked_term("How do I say in Portuguese?") is None  # nothing after it


def test_how_do_i_say_it_in_portuguese_asks_about_the_sentence_that_follows() -> None:
    said = "How do I say it in Portuguese? Ah, I'm going to be late for work today."
    assert asked_term(said) == "i'm going to be late for work today"
    assert focus_for(said, LEXICON, Language.EN) is Language.PT_BR
    assert asked_term("How do you say that? I don't know.") is None  # no language named: as before
    one_piece = 'How do I say it in Portuguese: "i\'m going to be late for work today"?'
    assert question_itself(said) == one_piece  # what the model is shown
    garfo = 'I will have to adiar our meeting. How do I say "garfo" in English?'
    assert question_itself(garfo) == 'How do I say "garfo" in English?'  # as before


@pytest.mark.parametrize(
    "said",
    [
        "Como se diz isso em inglês? Não sei.",
        "Como se diz isso em inglês? Deixa pra lá, vamos continuar.",
        "How do I say it in Portuguese? Never mind, let's move on to pricing.",
        "Eu esqueci o meu guarda-chuva. How do you say that in English? Do you know?",
    ],
)
def test_a_remark_after_the_question_is_not_what_it_asks_about(said: str) -> None:
    assert asked_term(said) is None


@pytest.mark.parametrize(
    ("said", "direct"),
    [
        ("Como se diz recibo?", True),
        ('Hum, how do I say in Portuguese, uh, "I will finish my work tomorrow"?', True),
        ("We need to, como é que fala, destravar a autenticação.", True),
        ("Limpar em inglês?", True),
        ("You need to learn how to say no to clients.", False),  # the words of asking, in passing
        ("Não sei como se fala com ele.", False),
        ("É como se diz, né.", False),
    ],
)
def test_asking_outright_and_the_words_of_asking_inside_a_statement(
    said: str, direct: bool
) -> None:
    assert asks_directly(said) is direct


@pytest.mark.parametrize(
    "said",
    [
        "I don't want to get it wrong, how do you pronounce it?",
        "Não quero errar, como se pronuncia?",
        "I don't have my glasses, can you say it out loud?",
    ],
)
def test_a_no_about_something_else_does_not_refuse_the_request(said: str) -> None:
    assert wants_to_hear(said)


@pytest.mark.parametrize(
    "said",
    [
        "Actually, I'm not even going to ask you to pronounce it for me.",  # it was pronounced
        "You don't need to pronounce it.",
        "Não precisa pronunciar, não quero ouvir de novo.",
    ],
)
def test_saying_one_will_not_ask_is_not_asking_to_hear_it(said: str) -> None:
    assert not wants_to_hear(said)
