"""The widened wake phrase through `decide()`: new greetings and a thank-you both reach Mochi."""

import pytest

from mochi_contracts import DecisionKind
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fixture_support import DecisionFixture, Expectation, decide_fixture


def _row(text: str, *, decision: DecisionKind, expr: str | None = None) -> DecisionFixture:
    expect = Expectation(decision=decision, expression=expr)
    return DecisionFixture(id="t", case="asks_mochi", text=text, expect=expect)


@pytest.mark.parametrize("greeting", ["Hey there", "Opa", "E aí", "Okay", "Yo", "Oh", "Ow"])
async def test_new_greetings_ask_mochi(greeting: str) -> None:
    fixture = _row(f"{greeting}, Mochi, what's the word for fila?", decision=DecisionKind.SPEAK)
    decision = await decide_fixture(fixture, FakeHintModel(None))
    assert decision.decision is DecisionKind.SPEAK
    assert decision.hint is not None and decision.hint.expression == "queue"


async def test_thanks_with_a_word_question_wakes_mochi() -> None:
    fixture = _row("Valeu Mochi, what's the word for fila?", decision=DecisionKind.SPEAK)
    decision = await decide_fixture(fixture, FakeHintModel(None))
    assert decision.decision is DecisionKind.SPEAK
