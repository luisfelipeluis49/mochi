"""The widened wake phrase through `decide()`: thanks wakes Mochi only outside a round."""

import pytest

from mochi_contracts import DecisionKind
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fixture_support import DecisionFixture, Expectation, decide_fixture


def _row(
    text: str, *, round_active: bool, decision: DecisionKind, expr: str | None = None
) -> DecisionFixture:
    expect = Expectation(decision=decision, expression=expr)
    return DecisionFixture(
        id="t", case="asks_mochi", text=text, expect=expect, round_active=round_active
    )


@pytest.mark.parametrize("greeting", ["Hey there", "Opa", "E aí", "Okay", "Yo", "Oh", "Ow"])
async def test_new_greetings_ask_mochi_even_in_a_round(greeting: str) -> None:
    fixture = _row(
        f"{greeting}, Mochi, what's the word for fila?",
        round_active=True,
        decision=DecisionKind.SPEAK,
    )
    decision = await decide_fixture(fixture, FakeHintModel(None))
    assert decision.decision is DecisionKind.SPEAK
    assert decision.hint is not None and decision.hint.expression == "queue"


async def test_thanks_with_a_word_question_wakes_mochi_outside_a_round() -> None:
    fixture = _row(
        "Valeu Mochi, what's the word for fila?", round_active=False, decision=DecisionKind.SPEAK
    )
    decision = await decide_fixture(fixture, FakeHintModel(None))
    assert decision.decision is DecisionKind.SPEAK


async def test_thanks_in_a_round_is_ignored() -> None:
    fixture = _row(
        "Thanks Mochi, what's the word for fila?", round_active=True, decision=DecisionKind.IGNORE
    )
    decision = await decide_fixture(fixture, FakeHintModel(None))
    assert decision.decision is DecisionKind.IGNORE
    assert decision.hint is None and decision.speak is None
