"""A training (D-68): a role-play from the person's history, no hints, about five minutes."""

from mochi_backend.gateway.practice_brief import PracticeBrief
from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS
from mochi_backend.gateway.session_service import TRAINING_HARD_STOP_SECONDS
from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus, ReviewWord
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.training_note import training_note
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.storage.factory import TeamStart
from mochi_backend.team.ledger import TeamLedger
from mochi_contracts import DecisionKind, Language, Reason, SessionMode, WordMoment
from tests.factories import make_turn
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_storage import FakeStorage
from tests.harness import make_harness
from tests.unit.test_review_mode import _card, _review


def _brain(clock: FakeClock, mochi: FakeCharacterModel) -> Intelligence:
    brain = Intelligence(clock=clock, ids=SequentialIdGenerator(), model=FakeHintModel())
    brain.speak_as(mochi)
    brain.session_started(True, Language.PT_BR, practice=["needed the word queue (fila)"])
    return brain


async def test_a_training_never_shows_a_hint_even_for_a_code_switch() -> None:
    mochi = FakeCharacterModel("Sure, when can you send it?")
    brain = _brain(FakeClock(), mochi)
    turn = make_turn("I need to adiar my meeting tomorrow.")
    decision = await brain.decide(turn, _review(_card("postpone")))
    assert decision.hint is None and decision.decision is DecisionKind.SPEAK
    assert [e.learning_event_id for e in decision.learning_events] == []


async def test_the_targets_stay_fixed_and_are_marked_used_once_said() -> None:
    mochi = FakeCharacterModel("Nice.")
    brain = _brain(FakeClock(), mochi)
    context = _review(_card("postpone"), _card("umbrella"))
    await brain.decide(make_turn("Hello there."), context)
    assert [w.used for w in mochi.requests[-1].review] == [False, False]
    await brain.decide(make_turn("We should postpone it."), context)
    # the card moved on in storage, but the training's targets do not change underneath it
    after = _review(_card("umbrella"))
    await brain.decide(make_turn("Okay."), after)
    last = mochi.requests[-1]
    assert [(w.expression, w.used) for w in last.review] == [
        ("postpone", True),
        ("umbrella", False),
    ]
    assert last.practice == ["needed the word queue (fila)"]


async def test_the_clock_reaches_mochi_and_it_wraps_up_after_four_minutes() -> None:
    clock, mochi = FakeClock(), FakeCharacterModel("Ok.")
    brain = _brain(clock, mochi)
    await brain.decide(make_turn("Hi."), _review(_card("postpone")))
    assert mochi.requests[-1].minute < 0.1
    clock.advance(270)
    await brain.decide(make_turn("Yes."), _review(_card("postpone")))
    assert 4.4 < mochi.requests[-1].minute < 4.6


def test_the_note_forbids_help_and_asks_for_a_positive_close() -> None:
    base = CharacterRequest(text="Hi", history=[], status=DeviceStatus(), reviewing=True)
    words = [
        ReviewWord(expression="postpone", meaning="adiar", used=True),
        ReviewWord(expression="queue"),
    ]
    early = training_note(base.model_copy(update={"review": words, "minute": 1.0}))
    assert "postpone (adiar, used)" in early and "queue (no translation, not used yet)" in early
    assert "no hint" in early and "NEW situation" in early and "They have no history yet" in early
    assert "feedback" not in early
    late = training_note(
        base.model_copy(update={"review": words, "minute": 4.2, "practice": ["x"]})
    )
    assert "positive" in late and "[bye]" in late and "Moments from their earlier" in late


def test_the_brief_holds_only_this_persons_moments_newest_first() -> None:
    def moment(word: str, user: str) -> WordMoment:
        return WordMoment(
            moment_id=f"m_{word}", company_id="demo", record_id=None, user_id=user,
            expression=word, meaning=f"{word}-pt", target_language=Language.EN,
            reason=Reason.CODE_SWITCH, at="2026-11-18T10:00:00.000Z", heard=f"I {word}",
        )  # fmt: skip

    start = TeamStart(moments=[moment("old", "ana"), moment("ben's", "ben"), moment("new", "ana")])
    ledger = TeamLedger(FakeStorage(), start, DEMO_COMPANY, DEMO_MEMBERS)
    lines = PracticeBrief(ledger).for_user("ana")
    assert [line.split()[3] for line in lines] == ["new", "old"]
    assert 'when they said "I new"' in lines[0]
    assert PracticeBrief(ledger).for_user("nobody") == []


async def test_a_training_ends_by_itself_when_its_time_is_up() -> None:
    harness = make_harness()
    runtime = await harness.container.registry.open("p-ana")
    await runtime.sessions.start(mode=SessionMode.REVIEW, user_id="ana")
    assert runtime.core.store.capturing
    harness.clock.advance(TRAINING_HARD_STOP_SECONDS + 1)
    await harness.scheduler.run_due()
    assert not runtime.core.store.capturing and "training_time_up" in harness.logger.names()
