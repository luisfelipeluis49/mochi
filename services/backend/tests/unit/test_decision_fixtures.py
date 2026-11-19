"""Runs every sentence in packages/fixtures/decisions.json through the real `Intelligence`."""

import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import BaseModel

from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, DecisionKind, Hint, SessionContext, Turn
from tests.factories import ANA, BEN, active_round, make_context, make_hint, make_turn
from tests.fakes.fake_clock import START, FakeClock
from tests.fakes.fake_hint_model import FakeHintModel

FIXTURES = Path(__file__).resolve().parents[4] / "packages" / "fixtures" / "decisions.json"


class Expectation(BaseModel):
    """What `decide()` should return for a fixture."""

    decision: DecisionKind
    expression: str | None = None
    reason: str | None = None
    target_user_id: str | None = None
    speak_text: str | None = None


class DecisionFixture(BaseModel):
    """One row of decisions.json."""

    id: str
    case: str
    text: str
    expect: Expectation
    history: list[str] = []
    hint_turns_ago: int | None = None
    round_active: bool = False
    participants: str | None = None
    model: ModelSuggestion | None = None


def _load() -> list[DecisionFixture]:
    return [DecisionFixture.model_validate(row) for row in json.loads(FIXTURES.read_text())]


def _context(fixture: DecisionFixture) -> tuple[SessionContext, Turn]:
    turns: list[Turn] = [make_turn(text, float(i)) for i, text in enumerate(fixture.history)]
    hints: list[Hint] = []
    if fixture.hint_turns_ago is not None:
        hints.append(make_hint(len(turns) - fixture.hint_turns_ago + 0.5))
    people = [ANA, BEN]
    if fixture.participants == "both_learning_en":
        people = [ANA, BEN.model_copy(update={"target_language": ANA.target_language})]
    context = make_context(
        participants=people,
        turns=turns,
        hints=hints,
        activity=active_round() if fixture.round_active else None,
    )
    return context, make_turn(fixture.text, float(len(turns)))


async def _decide(fixture: DecisionFixture) -> Decision:
    context, turn = _context(fixture)
    clock = FakeClock(START + timedelta(seconds=len(context.recent_turns)))
    brain = Intelligence(
        clock=clock, ids=SequentialIdGenerator(), model=FakeHintModel(fixture.model)
    )
    return await brain.decide(turn, context)


@pytest.mark.parametrize("fixture", _load(), ids=lambda f: f.id)
async def test_fixture_decision(fixture: DecisionFixture) -> None:
    decision = await _decide(fixture)
    assert decision.decision is fixture.expect.decision
    expected = fixture.expect
    if expected.decision is DecisionKind.IGNORE:
        assert decision.hint is None and decision.speak is None
        return
    hint = decision.hint
    assert hint is not None
    assert (hint.expression, hint.reason.value, hint.target_user_id) == (
        expected.expression,
        expected.reason,
        expected.target_user_id,
    )
    assert (decision.speak.text if decision.speak else None) == expected.speak_text


def test_every_case_has_three_hints_and_three_near_misses() -> None:
    rows = [f for f in _load() if f.case not in {"quiet_rules", "model"}]
    for case in {f.case for f in rows}:
        mine = [f for f in rows if f.case == case]
        hints = [f for f in mine if f.expect.decision is not DecisionKind.IGNORE]
        misses = [f for f in mine if f.expect.decision is DecisionKind.IGNORE]
        assert len(hints) >= 3, f"{case}: {len(hints)} hint fixtures; need at least 3"
        assert len(misses) >= 3, f"{case}: {len(misses)} near-misses; need at least 3"


def test_both_demo_sentences_are_fixtures() -> None:
    texts = {f.text for f in _load()}
    assert "I need to adiar my meeting tomorrow." in texts
    assert "I forgot my guarda-chuva at the office." in texts
