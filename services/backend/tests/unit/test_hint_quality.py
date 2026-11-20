"""What keeps a hint from being wrong or unwanted: the checks on the model's answer (D-29)."""

import asyncio
import json

from mochi_backend.intelligence.clear_cases import asked_term, asks_for_word, question_itself
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.http_client import HttpResponse
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, DecisionKind, Language, SessionContext
from tests.factories import make_context, make_hint, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient

GARFO = "Can you pass me the garfo, please?"
UMBRELLA = "I forgot my guarda-chuva at the office."


def _hint(**fields: object) -> ModelSuggestion:
    base = {"decision": "SHOW_HINT", "reason": "code_switch", "expression": "fork"}
    return ModelSuggestion.model_validate({**base, "meaning": "garfo", **fields})


async def _decided(suggestion: ModelSuggestion, text: str = GARFO) -> Decision:
    brain = Intelligence(
        clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel(suggestion)
    )
    return await brain.decide(make_turn(text), make_context())


async def test_a_hint_the_model_is_sure_of_is_shown() -> None:
    sure = _hint(confidence=0.95, expression_language="en", meaning_language="pt-BR")
    decision = await _decided(sure)
    assert decision.hint is not None and decision.hint.expression == "fork"


async def test_a_hint_the_model_doubts_is_not_shown() -> None:
    assert (await _decided(_hint(confidence=0.4))).decision is DecisionKind.IGNORE


async def test_a_hint_in_the_language_they_are_not_practising_is_not_shown() -> None:
    """Seen with a real model: "maybe a ranch?" in English talk got the hint "fazenda"."""
    wrong_side = _hint(expression="fazenda", meaning="ranch", expression_language="pt-BR")
    decision = await _decided(wrong_side, "Like, maybe they have a ranch? You know.")
    assert decision.decision is DecisionKind.IGNORE


async def test_a_synonym_for_a_word_of_the_same_language_is_not_a_hint() -> None:
    """Seen with a real model: "pass me the bathroom" got "restroom" and "bathroom key"."""
    heard = "Can you pass me the bathroom, please?"
    synonym = _hint(expression="restroom", meaning="bathroom", meaning_language="en")
    assert (await _decided(synonym, heard)).decision is DecisionKind.IGNORE
    longer = _hint(expression="bathroom key", meaning="bathroom")
    assert (await _decided(longer, heard)).decision is DecisionKind.IGNORE
    never_said = _hint(expression="toilet", meaning="banheiro")  # nobody said "banheiro"
    assert (await _decided(never_said, heard)).decision is DecisionKind.IGNORE
    false_friend = _hint(reason="look_alike", expression="toilet", meaning="bathroom")
    assert (await _decided(false_friend, heard)).decision is DecisionKind.IGNORE  # not from rules


async def test_someone_trying_out_a_word_they_were_given_is_not_stuck() -> None:
    """Seen live: "Molho para salada?" got "salad sauce" back."""
    echo = _hint(reason="says_unknown", expression="salad sauce", meaning="molho para salada")
    assert (await _decided(echo, "Molho para salada?")).decision is DecisionKind.IGNORE


def test_a_short_question_names_its_word_and_the_last_question_counts() -> None:
    assert asked_term("Esqueci a palavra. Limpar em inglês?") == "limpar"
    assert asked_term("Futs Como se fala Como se fala... Carteira em inglês.") == "carteira"
    assert asked_term("How do I say, like, salad sauce in, uh— Portuguese?") == "salad sauce"
    assert asked_term("Like, garfo in English?") == "garfo"
    for no_word_wanted in ("Can we talk in English?", "Você quer falar em português?"):
        assert asked_term(no_word_wanted) is None and not asks_for_word(no_word_wanted)


async def test_the_model_reads_only_the_sentence_that_asks() -> None:
    """Seen with a real model: it answered for "adiar", the other foreign word in the turn."""
    turn = 'I will have to cancelar our plan. How do I say "garfo" in English?'
    assert question_itself(turn) == 'How do I say "garfo" in English?'
    assert question_itself(GARFO) == GARFO
    model = FakeHintModel(_hint(reason="says_unknown"))
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=model)
    decision = await brain.decide(make_turn(turn), make_context())
    assert model.requests[0].text == 'How do I say "garfo" in English?'
    assert model.requests[0].asked_about == "garfo"
    assert decision.hint is not None and decision.hint.expression == "fork"


def test_fillers_and_sentence_starts_do_not_change_the_language_of_a_sentence() -> None:
    """Seen live: "Um, ... maybe a ranch?" was taken for Portuguese because of "um"."""
    lexicon = Lexicon.load()
    english = "Um, good question. Never. Like, maybe a ranch? You know."
    assert spoken_language(english, lexicon, Language.EN) is Language.EN
    assert spoken_language("Um, I don't know. I guess hamburger?", lexicon, Language.EN) is (
        Language.EN
    )
    portuguese = "Eu preciso de um umbrella porque está chovendo."
    assert spoken_language(portuguese, lexicon, Language.EN) is Language.PT_BR


def _after_a_hint(seconds_ago: float) -> SessionContext:
    """Two turns of talk, with a hint for "postpone" shown `seconds_ago` before the next turn."""
    turns = [make_turn("I need to adiar my meeting.", 0), make_turn("That sounds busy.", 12)]
    return make_context(turns=turns, hints=[make_hint(20 - seconds_ago)])


async def _next(text: str, context: SessionContext, cooldown: str) -> Decision:
    settings = IntelligenceSettings(hint_cooldown=cooldown)  # type: ignore[arg-type]
    brain = Intelligence(
        clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel(), settings=settings
    )
    return await brain.decide(make_turn(text, 20), context)


async def test_the_teams_cooldown_holds_a_second_word_back_for_two_turns() -> None:
    held = await _next(UMBRELLA, _after_a_hint(19.5), "two_turns")
    assert held.decision is DecisionKind.IGNORE


async def test_while_shown_lets_a_different_word_through_once_the_screen_is_free() -> None:
    """Seen live: "...esqueci minha wallet em casa" got nothing, two turns after another hint."""
    free = await _next(UMBRELLA, _after_a_hint(19.5), "while_shown")
    assert free.hint is not None and free.hint.expression == "umbrella"
    busy = await _next(UMBRELLA, _after_a_hint(5), "while_shown")  # the first is still up
    assert busy.decision is DecisionKind.IGNORE
    same = await _next("I must adiar it again.", _after_a_hint(19.5), "while_shown")
    assert same.decision is DecisionKind.IGNORE  # the same word twice in a row is spam


async def test_the_model_can_be_told_not_to_think_first_and_may_answer_ignore_briefly() -> None:
    body = json.dumps({"choices": [{"message": {"content": '{"decision": "IGNORE"}'}}]})
    http = FakeHttpClient([HttpResponse(200, body), HttpResponse(200, body)])
    request = ModelRequest(text=GARFO, recent_texts=[], focus=Language.EN, candidate_reasons=[])
    plain = OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0)
    answer = await plain.suggest(request)
    assert answer is not None and answer.decision == "IGNORE" and answer.reason is None
    fast = OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0).thinking("none")
    await fast.suggest(request)
    first, second = (post.payload for post in http.posts)
    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["temperature"] == 0 and "reasoning_effort" not in first
    assert second["reasoning_effort"] == "none" and "temperature" not in second


class _StallsOnce(FakeHintModel):
    """The first request hangs, as a stalled connection does; the second answers at once."""

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        first = not self.requests
        self.requests.append(request)
        if first:
            await asyncio.Event().wait()  # never answers; cancelled when the second one does
        return _hint()


async def test_a_stalled_request_is_asked_again_instead_of_costing_the_hint() -> None:
    """Seen in the benchmark: two answers in a row took the full two seconds, so no hint."""
    model = _StallsOnce()
    settings = IntelligenceSettings(hedge_after_seconds=0.0, model_timeout_seconds=1.0)
    brain = Intelligence(
        clock=FakeClock(), ids=SequentialIdGenerator(), model=model, settings=settings
    )
    decision = await brain.decide(make_turn(GARFO), make_context())
    assert decision.hint is not None and decision.hint.expression == "fork"
    assert len(model.requests) == 2


async def test_a_quick_answer_is_asked_for_once() -> None:
    model = FakeHintModel(_hint())
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=model)
    await brain.decide(make_turn(GARFO), make_context())
    assert len(model.requests) == 1
