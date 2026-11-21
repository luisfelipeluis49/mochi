"""Behaviour of `Intelligence.decide` beyond the fixtures: speak, model limits, saved words."""

import json

from mochi_backend.intelligence.clear_cases import (
    asked_term,
    unfinished_question,
    wanted_language,
)
from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.intelligence.quiet_rules import is_just_thinking
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.http_client import HttpResponse
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import DecisionKind, Language, LearningState, Reason
from tests.factories import make_context, make_hint, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient


def _brain(model: FakeHintModel | None = None) -> Intelligence:
    return Intelligence(
        clock=FakeClock(), ids=SequentialIdGenerator(), model=model or FakeHintModel()
    )


async def test_demo_sentence_creates_a_hint_for_ana_and_a_discovered_card() -> None:
    decision = await _brain().decide(
        make_turn("I need to adiar my meeting tomorrow."), make_context()
    )
    assert decision.decision is DecisionKind.SHOW_HINT and decision.hint is not None
    assert (decision.hint.expression, decision.hint.meaning) == ("postpone", "adiar")
    assert decision.hint.expires_at == "2026-11-19T16:00:08.000Z"
    [card] = decision.learning_events
    assert card.user_id == "ana" and card.learning_state is LearningState.DISCOVERED
    assert card.hint_id == decision.hint.hint_id


async def test_asking_mochi_speaks_and_also_shows_the_hint() -> None:
    decision = await _brain().decide(
        make_turn("Oi Mochi, what's the word for fila?"), make_context()
    )
    assert decision.decision is DecisionKind.SPEAK
    assert decision.speak is not None and decision.speak.text == "You can say: queue."
    assert decision.hint is not None and decision.hint.expression == "queue"
    assert len(decision.learning_events) == 1


async def test_a_word_already_saved_for_the_person_creates_no_second_card() -> None:
    brain, first_context = _brain(), make_context()
    first = await brain.decide(make_turn("I need to adiar my meeting."), first_context)
    saved = brain.apply(first.learning_events)
    context = first_context.model_copy(update={"learning_events": {"ana": saved, "ben": []}})
    again = await brain.decide(make_turn("I must adiar it again.", 30), context)
    assert again.hint is not None and again.learning_events == []


async def test_a_model_timeout_means_ignore() -> None:
    brain = _brain(FakeHintModel(TimeoutError("slow")))
    decision = await brain.decide(make_turn("How do you say cancelar?"), make_context())
    assert decision.decision is DecisionKind.IGNORE


async def test_unconfigured_or_ignoring_model_keeps_clear_cases_working() -> None:
    ignoring = FakeHintModel(ModelSuggestion(decision="IGNORE"))
    decision = await _brain(ignoring).decide(
        make_turn("I need to adiar my meeting."), make_context()
    )
    assert decision.decision is DecisionKind.SHOW_HINT
    assert ignoring.requests == []  # clear cases never call the model


async def test_the_model_looks_at_every_real_sentence_while_mochi_only_watches() -> None:
    """A word outside the lexicon carries no mark the rules could find: only the model can."""
    fork = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.CODE_SWITCH,
        expression="fork",
        meaning="garfo",
        confidence=0.9,
    )
    model = FakeHintModel(fork)
    decision = await _brain(model).decide(
        make_turn("Can you pass me the garfo, please?"), make_context()
    )
    assert decision.hint is not None and decision.hint.expression == "fork"
    assert len(model.requests) == 1


async def test_ordinary_talk_is_judged_too_and_stays_silent_when_the_model_says_so() -> None:
    model = FakeHintModel(ModelSuggestion(decision="IGNORE"))
    decision = await _brain(model).decide(make_turn("The weather is lovely today."), make_context())
    assert decision.decision is DecisionKind.IGNORE and len(model.requests) == 1


async def test_very_short_turns_are_not_worth_a_model_call() -> None:
    model = FakeHintModel(ModelSuggestion(decision="IGNORE"))
    for said in ("Yes.", "Thank you.", "Okay, sure."):
        await _brain(model).decide(make_turn(said), make_context())
    assert model.requests == []


async def test_with_the_wide_look_switched_off_ordinary_talk_never_reaches_the_model() -> None:
    model = FakeHintModel(ModelSuggestion(decision="SHOW_HINT", reason=None, expression="x"))
    brain = Intelligence(
        clock=FakeClock(),
        ids=SequentialIdGenerator(),
        model=model,
        settings=IntelligenceSettings(judge_every_sentence=False),
    )
    decision = await brain.decide(make_turn("The weather is lovely today."), make_context())
    assert decision.decision is DecisionKind.IGNORE and model.requests == []


async def test_a_hint_is_the_word_they_needed_not_the_one_they_said() -> None:
    """Seen with a real model: it returned the spoken word ("garfo") as the hint."""
    swapped = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.CODE_SWITCH,
        expression="garfo",
        meaning="fork",
        confidence=0.9,
    )
    decision = await _brain(FakeHintModel(swapped)).decide(
        make_turn("Can you pass me the garfo, please?"), make_context()
    )
    assert decision.hint is not None
    assert (decision.hint.expression, decision.hint.meaning) == ("fork", "garfo")
    echo = ModelSuggestion(decision="SHOW_HINT", reason=Reason.CODE_SWITCH, expression="garfo")
    nothing = await _brain(FakeHintModel(echo)).decide(
        make_turn("Can you pass me the garfo, please?"), make_context()
    )
    assert nothing.decision is DecisionKind.IGNORE


async def test_saying_the_expression_soon_after_upgrades_the_card_to_assisted() -> None:
    brain = _brain()
    context = make_context()
    first = await brain.decide(make_turn("I need to adiar my meeting.", 0), context)
    saved = brain.apply(first.learning_events)
    later = make_context(turns=[make_turn("ok", 1)]).model_copy(
        update={"learning_events": {"ana": saved, "ben": []}}
    )
    second = await brain.decide(make_turn("Let's postpone it.", 2), later)
    assert second.decision is DecisionKind.IGNORE
    assert [e.learning_state for e in second.learning_events] == [LearningState.ASSISTED]


def test_the_word_a_question_names_is_found() -> None:
    assert (
        asked_term('I will have to adiar our meeting. How do I say "garfo" in English?') == "garfo"
    )
    assert asked_term("Ben, como se diz recibo?") == "recibo"
    assert asked_term("Como se diz traffic jam em português?") == "traffic jam"
    assert asked_term("How do I say, like, salad sauce in, uh— Portuguese?") == "salad sauce"
    assert asked_term("How do you say… the thing for the rain?") == "the thing for the rain"
    assert asked_term("Futs Como se fala Como se fala...") is None  # nothing was named yet
    assert asked_term("I need to adiar my meeting.") is None


async def test_an_explicit_question_is_answered_for_the_word_it_names() -> None:
    """Seen live: the turn also held "adiar", and the hint came out as "postpone"."""
    fork = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.SAYS_UNKNOWN,
        expression="fork",
        meaning="garfo",
        confidence=0.9,
    )
    model = FakeHintModel(fork)
    decision = await _brain(model).decide(
        make_turn('I will have to adiar our meeting. How do I say "garfo" in English?'),
        make_context(),
    )
    assert decision.hint is not None and decision.hint.expression == "fork"
    assert model.requests[0].asked_about == "garfo"
    known = await _brain().decide(
        make_turn("I will have to go. How do I say guarda-chuva in English?"), make_context()
    )
    assert (
        known.hint is not None and known.hint.expression == "umbrella"
    )  # the lexicon still answers


async def test_someone_asking_outright_gets_a_hint_even_right_after_another() -> None:
    brain = _brain()
    hinted = [make_hint(0.5)]
    turns = [make_turn("I need to adiar my meeting.", 0), make_turn("Okay.", 1)]
    cooling = make_context(turns=turns, hints=hinted)
    unasked = await brain.decide(make_turn("I forgot my guarda-chuva at the office.", 2), cooling)
    assert unasked.decision is DecisionKind.IGNORE  # the cooldown still holds for unasked hints
    asked = await brain.decide(make_turn("How do you say guarda-chuva in English?", 2), cooling)
    assert asked.hint is not None and asked.hint.expression == "umbrella"


async def test_i_mean_at_the_start_of_a_turn_is_not_a_self_correction() -> None:
    """Seen live: "I mean garfo. Ai, nossa, eu esqueci minha wallet em casa." got nothing."""
    assert is_just_thinking("I need to, I mean, I want to adiar it.")
    assert is_just_thinking("No, I mean the other one.")
    assert not is_just_thinking("I mean garfo. Ai, nossa, eu esqueci minha wallet em casa.")
    decision = await _brain().decide(
        make_turn("I mean, I forgot my guarda-chuva at the office."), make_context()
    )
    assert decision.hint is not None and decision.hint.expression == "umbrella"


async def test_a_question_split_by_a_pause_is_read_as_one() -> None:
    """Seen live: "Como se fala..." then "Carteira em inglês." were two turns, both meaningless."""
    wallet = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.SAYS_UNKNOWN,
        expression="wallet",
        meaning="carteira",
        confidence=0.9,
    )
    model = FakeHintModel(wallet)
    first = make_turn("Como se fala...", 0)
    context = make_context(turns=[first])
    decision = await _brain(model).decide(make_turn("Carteira em inglês.", 4), context)
    assert decision.hint is not None and decision.hint.expression == "wallet"
    assert model.requests[0].asked_about == "carteira"
    assert model.requests[0].text == "Como se fala... Carteira em inglês."
    late = await _brain(FakeHintModel(wallet)).decide(make_turn("Carteira em inglês.", 60), context)
    assert late.decision is DecisionKind.IGNORE or late.hint is not None  # too far apart to be one
    assert unfinished_question("Como se fala...") and not unfinished_question("Como se diz fila?")


async def test_a_reason_the_model_made_up_does_not_cost_the_answer() -> None:
    """Seen with a real model: "reason": "asked_about" for an explicit question."""
    content = json.dumps(
        {
            "decision": "SHOW_HINT",
            "reason": "asked_about",
            "expression": "fork",
            "meaning": "garfo",
            "confidence": 0.9,
        }
    )
    body = json.dumps({"choices": [{"message": {"content": content}}]})
    http = FakeHttpClient([HttpResponse(200, body), HttpResponse(200, body)])
    model = OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0)
    asked = ModelRequest(
        text="How do I say garfo in English?",
        recent_texts=[],
        focus=Language.EN,
        candidate_reasons=[],
        asked_about="garfo",
    )
    answer = await model.suggest(asked)
    assert answer is not None and answer.reason is Reason.SAYS_UNKNOWN
    unasked = await model.suggest(asked.model_copy(update={"asked_about": None}))
    assert unasked is not None and unasked.reason is None


async def test_a_question_that_names_the_language_gets_its_hint_in_that_language() -> None:
    """Seen in a replay: "wallet" for "...carteira em inglês" was labelled Portuguese."""
    wallet = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.SAYS_UNKNOWN,
        expression="wallet",
        meaning="carteira",
        confidence=0.9,
    )
    model = FakeHintModel(wallet)
    decision = await _brain(model).decide(
        make_turn("Como se fala carteira em inglês?"), make_context()
    )
    assert decision.hint is not None and decision.hint.target_language is Language.EN
    assert decision.hint.target_user_id == "ana" and model.requests[0].focus is Language.EN
    assert wanted_language("How do I say garfo in, uh— Portuguese?") is Language.PT_BR
    assert wanted_language("I like speaking English with you.") is None
