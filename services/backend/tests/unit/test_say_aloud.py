"""Someone asks to hear a word: the one time Mochi speaks without its name (DECISIONS D-30)."""

from mochi_backend.intelligence.aloud import wants_to_hear
from mochi_backend.intelligence.clear_cases import asked_term, asks_for_word
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, DecisionKind, Hint, Language, SessionContext
from tests.factories import active_round, make_context, make_hint, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel

IGNORE = ModelSuggestion(decision="IGNORE")
# what was said on the Pi, word for word, half a minute after the hint "cortar o cabelo"
SEEN_LIVE = (
    "Acho legal, Boa, boa. É só isso por enquanto. Na verdade, você pode pronunciar para mim? "
    "É assim a pronunciação dessa tradução de cut my hair?"
)


def _haircut(shown_at: float = 30.0) -> Hint:
    words = {"expression": "cortar o cabelo", "meaning": "cut my hair"}
    return make_hint(shown_at).model_copy(update={**words, "target_language": Language.PT_BR})


def _after_the_hint(**changes: object) -> SessionContext:
    turns = [make_turn("Um lugar para... ai, como se fala... cut my hair.", 30)]
    return make_context(turns=turns, hints=[_haircut()]).model_copy(update=changes)


async def _said(text: str, context: SessionContext, woken: bool = False) -> Decision:
    brain = Intelligence(
        clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel(IGNORE)
    )
    brain.session_started(woken)
    return await brain.decide(make_turn(text, 60), context)


async def test_asked_to_pronounce_the_word_just_shown_mochi_says_it_and_shows_it_again() -> None:
    for request in (SEEN_LIVE, "Can you pronounce it for me?", "Ah, você não sabe pronunciar, né?"):
        decision = await _said(request, _after_the_hint())
        assert decision.decision is DecisionKind.SPEAK and decision.speak is not None, request
        assert decision.speak.text == "cortar o cabelo. cortar o cabelo."
        assert decision.speak.language is Language.PT_BR
        assert decision.hint is not None and decision.hint.expression == "cortar o cabelo"
        assert decision.hint.target_language is Language.PT_BR


async def test_with_no_recent_hint_there_is_nothing_to_say() -> None:
    assert (await _said("Can you pronounce it for me?", make_context())).speak is None
    long_ago = make_context(hints=[_haircut(shown_at=-200.0)])  # left the screen minutes ago
    assert (await _said("Can you pronounce it for me?", long_ago)).speak is None


async def test_mochi_stays_out_when_the_question_is_not_for_it() -> None:
    to_partner = await _said("Ben, can you pronounce it for me?", _after_the_hint())
    assert to_partner.speak is None
    in_a_round = await _said("Can you pronounce it?", _after_the_hint(activity=active_round()))
    assert in_a_round.speak is None
    # while Mochi is part of the talk it answers in its own words, not with the bare word
    chatting = await _said("Can you pronounce it for me?", _after_the_hint(), woken=True)
    assert chatting.speak is None or "cortar o cabelo. cortar" not in chatting.speak.text


async def test_a_quoted_word_is_read_out_unless_it_is_what_the_hint_stands_for() -> None:
    named = await _said('Você pode falar "reunião" para mim?', make_context())
    assert named.speak is not None and named.speak.text == "reunião. reunião."
    assert named.speak.language is Language.PT_BR and named.hint is None
    the_english = await _said('Como é a pronúncia de "cut my hair"?', _after_the_hint())
    assert the_english.speak is not None
    assert the_english.speak.text == "cortar o cabelo. cortar o cabelo."


async def test_a_word_found_in_the_same_turn_is_shown_and_said() -> None:
    decision = await _said("How do you pronounce guarda-chuva in English?", make_context())
    assert decision.hint is not None and decision.hint.expression == "umbrella"
    assert decision.speak is not None and decision.speak.text == "umbrella. umbrella."


def test_what_counts_as_asking_to_hear_a_word() -> None:
    for request in ("How do you pronounce that?", "Say it out loud.", "Fala pra mim de novo?"):
        assert wants_to_hear(request), request
    # people say these to each other
    for ordinary in ("Can you say that again?", "I don't know, isn't it late?", "What did he say?"):
        assert not wants_to_hear(ordinary), ordinary


# ---- two more things the same conversation showed ----


async def test_asking_how_to_say_a_dish_is_a_question_not_a_dish_dropped_in_on_purpose() -> None:
    """Seen live: "how do you say feijoada in English" was asked four times and got nothing."""
    for question in (
        "How do you say feijoada in English?",
        "How to say feijoada, the Brazilian dish feijoada in English?",
    ):
        assert asks_for_word(question), question
    assert asked_term("You know, how do you say feijoada in") == "feijoada"
    stew = ModelSuggestion.model_validate(
        {
            "decision": "SHOW_HINT",
            "reason": "says_unknown",
            "expression": "bean stew",
            "confidence": 0.9,
        }
    )
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel(stew))
    asked = await brain.decide(make_turn("How do you say feijoada in English?"), make_context())
    assert asked.hint is not None and asked.hint.expression == "bean stew"
    eaten = await brain.decide(make_turn("We had feijoada yesterday."), make_context())
    assert eaten.decision is DecisionKind.IGNORE


async def test_two_borrowed_words_do_not_change_the_language_of_the_sentence() -> None:
    """Seen live: "The reunião will atrasar." counted as Portuguese and got no hint."""
    heard = "The reunião will atrasar."
    assert spoken_language(heard, Lexicon.load(), Language.PT_BR) is Language.EN
    decision = await _said(heard, make_context())
    assert decision.hint is not None and decision.hint.target_language is Language.EN
