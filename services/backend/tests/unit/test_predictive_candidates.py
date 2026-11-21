"""Up to three candidate words for a hint with no single known answer (Mochi AR, PROPOSAL).

Only trails_off, restarts and talks_around qualify (AGENTS 7.1 cases 5-6): there the speaker
named no word, so more than one completion may fit. Every other reason keeps one word, as
before, so a client that does not know `candidates`/`context` still shows the same hint.
"""

import json

from mochi_backend.intelligence.model_port import CandidateSuggestion, ModelSuggestion
from mochi_backend.intelligence.openai_hint_model import _suggestion
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import DecisionKind, Reason
from tests.factories import make_context, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel

TRAILED_OFF = "I wanted to go, but..."


def _brain(model: ModelSuggestion | None) -> Intelligence:
    return Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel(model))


def _three_candidates() -> ModelSuggestion:
    return ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.TRAILS_OFF,
        expression="although",
        meaning="embora",
        confidence=0.8,
        candidates=[
            CandidateSuggestion(expression="although", meaning="embora"),
            CandidateSuggestion(expression="unfortunately", meaning="infelizmente"),
            CandidateSuggestion(expression="instead", meaning="em vez disso"),
        ],
    )


async def test_an_open_search_hint_carries_its_candidates_and_context() -> None:
    decision = await _brain(_three_candidates()).decide(make_turn(TRAILED_OFF), make_context())
    hint = decision.hint
    assert decision.decision is DecisionKind.SHOW_HINT and hint is not None
    assert hint.context == TRAILED_OFF
    assert [c.expression for c in (hint.candidates or [])] == [
        "although",
        "unfortunately",
        "instead",
    ]
    assert hint.expression == "although"  # the primary stays the top-level field too


async def test_a_repeated_or_empty_candidate_is_dropped_and_capped_at_three() -> None:
    suggestion = _three_candidates().model_copy(
        update={
            "candidates": [
                CandidateSuggestion(expression="Although", meaning="embora"),  # same as primary
                CandidateSuggestion(expression="", meaning="nothing"),  # empty
                CandidateSuggestion(expression="unfortunately", meaning="infelizmente"),
                CandidateSuggestion(expression="instead", meaning="em vez disso"),
                CandidateSuggestion(expression="regardless", meaning="de todo jeito"),  # a 4th
            ]
        }
    )
    decision = await _brain(suggestion).decide(make_turn(TRAILED_OFF), make_context())
    hint = decision.hint
    assert hint is not None
    expressions = [c.expression for c in (hint.candidates or [])]
    assert expressions == ["although", "unfortunately", "instead"]


async def test_a_reason_with_one_right_word_never_gets_candidates() -> None:
    """code_switch has a known translation: extra candidates would be invented, not found."""
    suggestion = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.CODE_SWITCH,
        expression="fork",
        meaning="garfo",
        confidence=0.9,
        candidates=[CandidateSuggestion(expression="spoon", meaning="colher")],
    )
    decision = await _brain(suggestion).decide(
        make_turn("Can you pass me the garfo, please?"), make_context()
    )
    hint = decision.hint
    assert hint is not None
    assert hint.candidates is None and hint.context is None


def test_the_real_adapter_drops_a_malformed_candidate_without_losing_the_hint() -> None:
    content = json.dumps(
        {
            "decision": "SHOW_HINT",
            "reason": "trails_off",
            "expression": "although",
            "meaning": "embora",
            "confidence": 0.8,
            "candidates": [
                {"expression": "although", "meaning": "embora"},
                {"expression": 7, "meaning": "not a string expression"},  # dropped
                "not even an object",  # dropped
                {"meaning": "no expression key"},  # dropped
                {"expression": "instead"},  # kept, meaning None
            ],
        }
    )
    suggestion = _suggestion(content, asked=False)
    assert suggestion.decision == "SHOW_HINT"
    assert [c.expression for c in suggestion.candidates] == ["although", "instead"]
    assert suggestion.candidates[1].meaning is None


def test_the_real_adapter_tolerates_a_non_list_candidates_field() -> None:
    content = json.dumps(
        {"decision": "SHOW_HINT", "expression": "although", "candidates": "although"}
    )
    assert _suggestion(content, asked=False).candidates == []
