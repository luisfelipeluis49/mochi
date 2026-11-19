"""Quiet rules (AGENTS 7.2), memory, and learning-state transitions (7.4)."""

from datetime import timedelta

import pytest

from mochi_backend.intelligence.learning_rules import assisted_updates, with_state
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.intelligence.quiet_rules import (
    cooldown_active,
    is_just_thinking,
    is_serious,
    quiet_reason,
    round_is_active,
)
from mochi_backend.platform.clock import iso_z
from mochi_contracts import (
    Language,
    LearningEvent,
    LearningState,
    Reason,
    SessionMode,
    StateChange,
)
from tests.factories import active_round, make_context, make_hint, make_turn
from tests.fakes.fake_clock import START, FakeClock

LEXICON = Lexicon.load()


def _event(
    expression: str = "postpone", at: float = 0.5, user: str | None = "ana"
) -> LearningEvent:
    stamp = iso_z(START + timedelta(seconds=at))
    return LearningEvent(
        learning_event_id=f"learn_{expression}",
        user_id=user,
        target_language=Language.EN,
        expression=expression,
        meaning="adiar",
        detection_signal=Reason.CODE_SWITCH,
        hint_id="hint_1",
        learning_state=LearningState.DISCOVERED,
        state_history=[StateChange(learning_state=LearningState.DISCOVERED, at=stamp)],
    )


def test_round_is_active_only_during_active_round() -> None:
    assert round_is_active(make_context(activity=active_round()))
    assert not round_is_active(make_context())


def test_cooldown_covers_the_two_turns_after_a_hint() -> None:
    hint = make_hint(0.5)
    two_turns = [make_turn("a", 0), make_turn("b", 1)]
    three_turns = [make_turn("a", 0), make_turn("b", 1), make_turn("c", 2)]
    assert cooldown_active(make_context(turns=two_turns, hints=[hint]), 8.0)
    assert not cooldown_active(make_context(turns=three_turns, hints=[hint]), 8.0)
    assert not cooldown_active(make_context(), 8.0)


@pytest.mark.parametrize(
    "said", ["My father died last year.", "She has cancer.", "Foi um funeral triste."]
)
def test_serious_talk_is_quiet(said: str) -> None:
    assert is_serious(said)


@pytest.mark.parametrize(
    "said", ["Hmm.", "Um, well…", "Let me think.", "I need, I mean, I want tea."]
)
def test_thinking_and_self_correction_are_quiet(said: str) -> None:
    assert is_just_thinking(said)


def test_quiet_reason_names_the_first_rule() -> None:
    context = make_context(activity=active_round())
    assert quiet_reason("I need to adiar it", context, LEXICON, 8.0) == "round_active"
    assert quiet_reason("I need to adiar it", make_context(), LEXICON, 8.0) is None
    assert quiet_reason("We had feijoada.", make_context(), LEXICON, 8.0) == "deliberate_switch"


def test_with_state_appends_history() -> None:
    upgraded = with_state(_event(), LearningState.ASSISTED, "2026-11-19T16:00:09.000Z")
    assert upgraded.learning_state is LearningState.ASSISTED
    assert [s.learning_state for s in upgraded.state_history] == [
        LearningState.DISCOVERED,
        LearningState.ASSISTED,
    ]


def _assist(
    text: str, turns_after: int, mode: SessionMode = SessionMode.TOGETHER
) -> list[LearningEvent]:
    turns = [make_turn(f"t{i}", float(i + 1)) for i in range(turns_after)]
    context = make_context(turns=turns, mode=mode)
    context = context.model_copy(update={"learning_events": {"ana": [_event()], "ben": []}})
    return assisted_updates(make_turn(text, 10), context, FakeClock())


def test_expression_said_within_three_turns_becomes_assisted() -> None:
    updated = _assist("I will postpone it.", turns_after=2)
    assert [e.learning_state for e in updated] == [LearningState.ASSISTED]


def test_expression_said_after_three_turns_stays_discovered() -> None:
    assert _assist("I will postpone it.", turns_after=3) == []


def test_other_words_and_activity_mode_do_not_assist() -> None:
    assert _assist("Nice weather.", turns_after=1) == []
    assert _assist("I will postpone it.", turns_after=1, mode=SessionMode.ACTIVITY) == []


def test_memory_store_creates_updates_and_lists_newest_first() -> None:
    store = MemoryStore()
    first, second = _event("postpone"), _event("umbrella")
    assert store.apply([first, second]) == [first, second]
    assert [e.expression for e in store.words_for("ana")] == ["umbrella", "postpone"]
    upgraded = with_state(first, LearningState.ASSISTED, "2026-11-19T16:00:09.000Z")
    store.apply([upgraded])
    assert store.words_for("ana")[1].learning_state is LearningState.ASSISTED


def test_memory_store_hides_events_with_no_user_and_resets() -> None:
    store = MemoryStore()
    store.apply([_event(user=None)])
    assert store.words_for("ana") == [] and store.words_for("ben") == []
    store.apply([_event()])
    store.reset()
    assert store.words_for("ana") == []
