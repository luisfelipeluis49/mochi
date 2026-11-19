"""Loads packages/fixtures/decisions.json and runs a fixture through `Intelligence`.

Shared by the pytest runner and `scripts/eval_intelligence.py` (which swaps in the real model).
"""

import json
from datetime import timedelta
from pathlib import Path

from pydantic import BaseModel

from mochi_backend.intelligence.model_port import HintModel, ModelSuggestion
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, DecisionKind, Hint, SessionContext, Turn
from tests.factories import ANA, BEN, active_round, make_context, make_hint, make_turn
from tests.fakes.fake_clock import START, FakeClock

FIXTURES_FILE = Path(__file__).resolve().parents[3] / "packages" / "fixtures" / "decisions.json"


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


def load_fixtures() -> list[DecisionFixture]:
    """Every fixture in decisions.json."""
    return [DecisionFixture.model_validate(row) for row in json.loads(FIXTURES_FILE.read_text())]


def build_case(fixture: DecisionFixture) -> tuple[SessionContext, Turn]:
    """The context (history one second apart, optional recent hint) and the turn under test."""
    turns = [make_turn(text, float(i)) for i, text in enumerate(fixture.history)]
    hints: list[Hint] = []
    if fixture.hint_turns_ago is not None:
        hints.append(make_hint(len(turns) - fixture.hint_turns_ago + 0.5))
    people = [ANA, BEN]
    if fixture.participants == "both_learning_en":
        people = [ANA, BEN.model_copy(update={"target_language": ANA.target_language})]
    activity = active_round() if fixture.round_active else None
    context = make_context(participants=people, turns=turns, hints=hints, activity=activity)
    return context, make_turn(fixture.text, float(len(turns)))


async def decide_fixture(fixture: DecisionFixture, model: HintModel) -> Decision:
    """Run one fixture through a fresh `Intelligence` that uses `model`."""
    context, turn = build_case(fixture)
    clock = FakeClock(START + timedelta(seconds=len(context.recent_turns)))
    brain = Intelligence(clock=clock, ids=SequentialIdGenerator(), model=model)
    return await brain.decide(turn, context)


def matches(decision: Decision, expected: Expectation) -> bool:
    """True when the decision equals the expectation (decision kind, hint fields, spoken line)."""
    if decision.decision is not expected.decision:
        return False
    if expected.decision is DecisionKind.IGNORE:
        return decision.hint is None and decision.speak is None
    hint = decision.hint
    if hint is None:
        return False
    got = (hint.expression, hint.reason.value, hint.target_user_id)
    spoken = decision.speak.text if decision.speak else None
    return got == (expected.expression, expected.reason, expected.target_user_id) and (
        spoken == expected.speak_text
    )
