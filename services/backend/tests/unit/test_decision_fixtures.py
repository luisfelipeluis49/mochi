"""Runs every sentence in packages/fixtures/decisions.json through the real `Intelligence`."""

import pytest

from mochi_contracts import DecisionKind
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fixture_support import DecisionFixture, decide_fixture, load_fixtures, matches


@pytest.mark.parametrize("fixture", load_fixtures(), ids=lambda f: f.id)
async def test_fixture_decision(fixture: DecisionFixture) -> None:
    decision = await decide_fixture(fixture, FakeHintModel(fixture.model))
    assert matches(decision, fixture.expect), f"{fixture.id}: got {decision!r}"


def test_every_case_has_three_hints_and_three_near_misses() -> None:
    rows = [f for f in load_fixtures() if f.case not in {"quiet_rules", "model"}]
    for case in {f.case for f in rows}:
        mine = [f for f in rows if f.case == case]
        hints = [f for f in mine if f.expect.decision is not DecisionKind.IGNORE]
        misses = [f for f in mine if f.expect.decision is DecisionKind.IGNORE]
        assert len(hints) >= 3, f"{case}: {len(hints)} hint fixtures; need at least 3"
        assert len(misses) >= 3, f"{case}: {len(misses)} near-misses; need at least 3"


def test_both_demo_sentences_are_fixtures() -> None:
    texts = {f.text for f in load_fixtures()}
    assert "I need to adiar my meeting tomorrow." in texts
    assert "I forgot my guarda-chuva at the office." in texts
