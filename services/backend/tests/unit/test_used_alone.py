""" "Used on your own": a saved word said in a later meeting with no hint (DECISIONS D-55)."""

from datetime import timedelta

from mochi_backend.intelligence.learning_rules import assisted_updates, used_alone
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.clock import iso_z
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import LearningState, Utterance
from tests.factories import make_context, make_turn
from tests.fakes.fake_clock import START, FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.unit.test_team_view import card

BEGAN = START
NOW = iso_z(START + timedelta(minutes=30))


def said(user: str | None, text: str, minute: int = 1) -> Utterance:
    return Utterance(
        utterance_id=f"seg_{minute}",
        company_id="demo",
        record_id="rec_1",
        user_id=user,
        text=text,
        at=iso_z(START + timedelta(minutes=minute)),
    )


OLD = card("postpone", "ana", days_ago=3)  # test_team_view's NOW is two days after START


def test_a_word_from_an_earlier_session_said_by_its_person_is_used_on_their_own() -> None:
    [used] = used_alone([OLD], [said("ana", "Let's postpone the review.")], set(), BEGAN, NOW)
    assert used.learning_state is LearningState.USED_INDEPENDENTLY
    assert [c.learning_state for c in used.state_history][-1] is LearningState.USED_INDEPENDENTLY
    assert used.state_history[-1].at == NOW


def test_it_does_not_count_when_someone_else_or_nobody_known_said_it() -> None:
    for speaker in ("ben", None):
        assert used_alone([OLD], [said(speaker, "Let's postpone it.")], set(), BEGAN, NOW) == []


def test_it_does_not_count_when_the_word_was_shown_in_this_meeting_or_touched_today() -> None:
    meeting = [said("ana", "Let's postpone it.")]
    assert used_alone([OLD], meeting, {"postpone"}, BEGAN, NOW) == []
    today = card("postpone", "ana", days_ago=1)  # a day after START: during "this" session
    assert used_alone([today], meeting, set(), BEGAN, NOW) == []
    done = card("postpone", "ana", LearningState.USED_INDEPENDENTLY, days_ago=3)
    assert used_alone([done], meeting, set(), BEGAN, NOW) == []


def test_repeating_a_colleagues_word_is_not_remembering_it() -> None:
    echo = [said("ben", "Should we postpone it?", 1), said("ana", "Yes, postpone it.", 2)]
    assert used_alone([OLD], echo, set(), BEGAN, NOW) == []
    later = [
        *echo,
        said("ben", "Fine.", 3),
        said("ben", "Next.", 4),
        said("ana", "I will postpone it.", 5),
    ]
    assert len(used_alone([OLD], later, set(), BEGAN, NOW)) == 1


def test_the_brain_proposes_it_for_every_recognised_speaker() -> None:
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel())
    brain.apply([OLD, card("receipt", "ana", days_ago=3), card("fila", "ben", days_ago=3)])
    meeting = [
        said("ana", "We should postpone it.", 1),
        said("ana", "I kept the receipt.", 2),
        said("ben", "A fila estava enorme.", 3),
    ]
    proposals = brain.used_alone(meeting, ["Receipt"], iso_z(BEGAN))  # shown: read off the screen
    assert sorted(p.expression for p in proposals) == ["fila", "postpone"]
    assert brain.used_alone([], [], iso_z(BEGAN)) == []


def test_a_card_from_an_earlier_session_is_not_used_with_help_in_the_first_sentences() -> None:
    """Three turns were counted from this session's turns only, so last week's card said in a
    new meeting's first sentence became ASSISTED with no hint in sight."""
    context = make_context().model_copy(update={"learning_events": {"ana": [OLD]}})
    turn = make_turn("Let's postpone the review.", 5)
    assert assisted_updates(turn, context, FakeClock(), 8.0) == []
