"""Behaviour of `Intelligence.decide` beyond the fixtures: speak, model limits, saved words."""

from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import DecisionKind, LearningState
from tests.factories import make_context, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel


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


async def test_model_is_not_called_for_ordinary_talk() -> None:
    model = FakeHintModel(ModelSuggestion(decision="SHOW_HINT", reason=None, expression="x"))
    decision = await _brain(model).decide(make_turn("The weather is lovely today."), make_context())
    assert decision.decision is DecisionKind.IGNORE and model.requests == []


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
