"""The team view: every member's learning data added up, with nobody's words or sentences."""

from datetime import timedelta

from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS, DEMO_USERS
from mochi_backend.platform.clock import iso_z
from mochi_backend.team.facts import TeamFacts
from mochi_backend.team.gaps import gaps_in, reason_counts, share_of, split_by_kind
from mochi_backend.team.highlights import highlights_for
from mochi_backend.team.progress import funnel_of, member_rows
from mochi_backend.team.team_view import (
    active_people,
    minutes_of,
    monday_of,
    team_insights,
    totals_of,
    weeks_of,
)
from mochi_contracts import (
    Language,
    LearningEvent,
    LearningFunnel,
    LearningState,
    Reason,
    SessionMode,
    SessionRecord,
    SpeakingShare,
    StateChange,
    WordMoment,
)
from tests.fakes.fake_clock import START

NOW = START + timedelta(days=2)  # Saturday 2026-11-21; START is Thursday the 19th


def at(days_ago: float, minutes: float = 0.0) -> str:
    """A timestamp `days_ago` days before NOW, `minutes` later."""
    return iso_z(NOW - timedelta(days=days_ago) + timedelta(minutes=minutes))


def moment(
    word: str, user: str | None, days_ago: float = 1.0, reason: Reason = Reason.CODE_SWITCH
) -> WordMoment:
    return WordMoment(
        moment_id=f"mom_{word}_{user}_{days_ago}",
        company_id="demo",
        record_id="rec_1",
        user_id=user,
        expression=word,
        meaning=f"{word}-pt",
        target_language=Language.EN,
        reason=reason,
        at=at(days_ago),
        heard=f"I need to {word}-pt it",
    )


def record(
    mode: SessionMode = SessionMode.MEETING,
    days_ago: float = 1.0,
    speaking: dict[str | None, int] | None = None,
    people: list[str] | None = None,
) -> SessionRecord:
    shares = [SpeakingShare(user_id=u, turns=t, words=t * 6) for u, t in (speaking or {}).items()]
    return SessionRecord(
        record_id=f"rec_{mode.value}_{days_ago}",
        company_id="demo",
        session_id="demo",
        mode=mode,
        started_at=at(days_ago),
        ended_at=at(days_ago, minutes=30.4),
        participants=people or ["ana", "ben"],
        speaking=shares,
    )


def card(word: str, user: str, *states: LearningState, days_ago: float = 1.0) -> LearningEvent:
    path = [LearningState.DISCOVERED, *states]
    return LearningEvent(
        learning_event_id=f"learn_{word}_{user}",
        user_id=user,
        target_language=Language.EN,
        expression=word,
        meaning=None,
        detection_signal=Reason.CODE_SWITCH,
        hint_id=None,
        learning_state=path[-1],
        state_history=[StateChange(learning_state=s, at=at(days_ago)) for s in path],
    )


def facts(
    moments: list[WordMoment] | None = None,
    records: list[SessionRecord] | None = None,
    cards: dict[str, list[LearningEvent]] | None = None,
) -> TeamFacts:
    users = {user.user_id: user for user in DEMO_USERS}
    return TeamFacts(DEMO_COMPANY, DEMO_MEMBERS, users, records or [], moments or [], cards or {})


def test_share_of_rounds_and_survives_nothing() -> None:
    assert share_of(1, 3) == 0.333 and share_of(0, 0) == 0.0


def test_reason_counts_are_ordered_by_how_often() -> None:
    moments = [
        moment("postpone", "ana"),
        moment("umbrella", "ana"),
        moment("intend", "ana", reason=Reason.LOOK_ALIKE),
    ]
    counted = reason_counts(moments)
    assert [(c.reason, c.times, c.share) for c in counted] == [
        (Reason.CODE_SWITCH, 2, 0.667),
        (Reason.LOOK_ALIKE, 1, 0.333),
    ]
    assert reason_counts([]) == []


def test_a_gap_counts_people_and_times_and_never_names_anyone() -> None:
    moments = [
        moment("postpone", "ana", days_ago=3),
        moment("Postpone", "ana", days_ago=2),
        moment("postpone", "ben", days_ago=1),
        moment("postpone", None, days_ago=0.5),  # an unknown voice: counted, but nobody's
        moment("umbrella", "ana"),
    ]
    first, second = gaps_in(moments)
    assert (first.expression, first.people, first.times) == ("postpone", 2, 4)
    assert first.last_at == at(0.5) and first.meaning == "postpone-pt"
    assert (second.expression, second.people, second.times) == ("umbrella", 1, 1)
    assert "ana" not in first.model_dump_json() and "I need to" not in first.model_dump_json()


def test_a_small_teams_list_can_leave_out_what_one_person_needed() -> None:
    moments = [moment("postpone", "ana"), moment("postpone", "ben"), moment("umbrella", "ana")]
    assert [gap.expression for gap in gaps_in(moments, min_people=2)] == ["postpone"]
    assert len(gaps_in(moments, top=1)) == 1


def test_what_only_unknown_voices_needed_is_still_shown_unless_a_threshold_is_set() -> None:
    """A phone's microphone recognises nobody: its meeting must not come out empty."""
    unknown = [moment("deadline", None), moment("deadline", None, days_ago=2)]
    [gap] = gaps_in(unknown)
    assert (gap.expression, gap.people, gap.times) == ("deadline", 0, 2)
    assert gaps_in(unknown, min_people=2) == []


def test_false_friends_are_mistakes_not_missing_words() -> None:
    wrong = moment("intend", "ana", reason=Reason.LOOK_ALIKE)
    missing = moment("postpone", "ana")
    assert split_by_kind([wrong, missing]) == ([missing], [wrong])


def test_minutes_of_a_session_and_of_one_still_running() -> None:
    assert minutes_of(record()) == 30
    assert minutes_of(record().model_copy(update={"ended_at": None})) == 0


def test_only_people_who_did_something_are_active() -> None:
    spoke = record(speaking={"ana": 3, None: 2})
    listed_only = facts(records=[spoke])
    assert active_people(listed_only) == {"ana"}  # Ben was on the list and said nothing
    review = record(SessionMode.REVIEW, people=["ben"])
    assert active_people(facts(records=[review])) == {"ben"}
    stranger = facts(moments=[moment("postpone", "zed")])
    assert active_people(stranger) == set()  # not a member


def test_totals_count_meetings_reviews_minutes_moments_and_words() -> None:
    known = facts(
        moments=[moment("postpone", "ana"), moment("POSTPONE", "ben"), moment("umbrella", "ana")],
        records=[record(speaking={"ana": 4}), record(SessionMode.REVIEW, people=["ana"])],
    )
    totals = totals_of(known)
    assert (totals.members, totals.active_members) == (2, 2)
    assert (totals.meetings, totals.reviews, totals.meeting_minutes) == (1, 1, 30)
    assert (totals.moments, totals.words) == (3, 2)


def test_the_funnel_looks_at_the_whole_history_of_a_card() -> None:
    cards = {
        "ana": [
            card("postpone", "ana", LearningState.ASSISTED, LearningState.REINFORCED),
            card("umbrella", "ana", LearningState.REINFORCED),  # recalled without ever being helped
            card("queue", "ana"),
        ],
        "ben": [card("fila", "ben", LearningState.ASSISTED)],
    }
    assert funnel_of(cards) == LearningFunnel(
        discovered=4, assisted=3, reinforced=2, used_independently=0
    )


def test_a_members_row_holds_counts_and_no_words() -> None:
    known = facts(
        moments=[moment("postpone", "ana"), moment("umbrella", "ana", days_ago=0.25)],
        records=[
            record(speaking={"ana": 5, "ben": 2}, days_ago=3),
            record(speaking={"ben": 1}, days_ago=2),
            record(SessionMode.REVIEW, people=["ana"], days_ago=1),
        ],
        cards={"ana": [card("postpone", "ana", LearningState.ASSISTED), card("umbrella", "ana")]},
    )
    ana, ben = member_rows(known)
    assert (ana.display_name, ana.role.value) == ("Ana", "admin")
    assert (ana.meetings, ana.reviews, ana.speaking_turns, ana.moments) == (1, 1, 5, 2)
    assert (ana.words, ana.assisted, ana.reinforced) == (2, 1, 0)
    assert ana.last_active_at == at(0.25)
    assert (ben.meetings, ben.speaking_turns, ben.words, ben.moments) == (2, 3, 0, 0)
    assert "postpone" not in ana.model_dump_json()


def test_a_meeting_counts_for_someone_whose_word_it_held_even_with_no_voice_recognised() -> None:
    phone_meeting = record()  # a phone's microphone: nobody's voice is known
    theirs = moment("postpone", "ana").model_copy(update={"record_id": phone_meeting.record_id})
    ana, ben = member_rows(facts(moments=[theirs], records=[phone_meeting]))
    assert (ana.meetings, ana.speaking_turns, ben.meetings) == (1, 0, 0)


def test_someone_who_did_nothing_has_no_last_activity() -> None:
    _, ben = member_rows(facts(moments=[moment("postpone", "ana")]))
    assert ben.last_active_at is None and ben.meetings == 0


def test_weeks_start_on_monday_and_quiet_weeks_are_kept() -> None:
    assert monday_of(NOW).date().isoformat() == "2026-11-16"
    known = facts(
        moments=[moment("postpone", "ana", days_ago=1), moment("umbrella", "ben", days_ago=9)],
        records=[record(days_ago=1), record(SessionMode.REVIEW, days_ago=1)],
        cards={"ana": [card("postpone", "ana", days_ago=1)]},
    )
    weeks = weeks_of(known, NOW - timedelta(days=20), NOW)
    assert [w.week_start for w in weeks] == ["2026-10-26", "2026-11-02", "2026-11-09", "2026-11-16"]
    assert [(w.meetings, w.moments, w.people, w.new_words) for w in weeks] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 1, 1, 0),
        (1, 1, 1, 1),
    ]


def test_highlights_name_what_deserves_attention() -> None:
    gaps = gaps_in(
        [moment("postpone", "ana"), moment("postpone", "ben")]
        + [moment("deadline", "ana", days_ago=d) for d in (1, 2, 3)]
    )
    friends = gaps_in([moment("intend", "ana", reason=Reason.LOOK_ALIKE)])
    cards = {
        "ana": [card("postpone", "ana", LearningState.ASSISTED), card("deadline", "ana")],
        "ben": [card("fila", "ben", LearningState.REINFORCED)],
    }
    found = {h.kind: h for h in highlights_for(gaps, friends, funnel_of(cards), cards)}
    assert (found["shared_gap"].expression, found["shared_gap"].people) == ("postpone", 2)
    assert (found["repeated_gap"].expression, found["repeated_gap"].times) == ("deadline", 3)
    assert found["false_friend"].expression == "intend"
    assert (found["words_sticking"].times, found["words_sticking"].share) == (2, 0.667)
    assert (found["review_backlog"].people, found["review_backlog"].times) == (1, 2)


def test_with_nothing_learned_yet_there_is_nothing_to_highlight() -> None:
    empty = LearningFunnel(discovered=0, assisted=0, reinforced=0, used_independently=0)
    assert highlights_for([], [], empty, {}) == []


def test_the_team_view_covers_its_period_and_keeps_sentences_out() -> None:
    known = facts(
        moments=[
            moment("postpone", "ana", days_ago=1),
            moment("postpone", "ben", days_ago=2),
            moment("intend", "ana", days_ago=3, reason=Reason.LOOK_ALIKE),
            moment("receipt", "ana", days_ago=45),  # before the period
        ],
        records=[record(speaking={"ana": 5}, days_ago=1), record(days_ago=60)],
        cards={"ana": [card("postpone", "ana", LearningState.ASSISTED)]},
    )
    view = team_insights(known, NOW, period_days=30)
    assert (view.totals.meetings, view.totals.moments, view.totals.words) == (1, 3, 2)
    assert [g.expression for g in view.shared_gaps] == ["postpone"]
    assert [g.expression for g in view.false_friends] == ["intend"]
    assert [s.reason for s in view.signals] == [Reason.CODE_SWITCH, Reason.LOOK_ALIKE]
    assert view.funnel.assisted == 1 and len(view.weekly) == 5
    assert view.generated_at == iso_z(NOW) and view.period_days == 30
    assert "I need to" not in view.model_dump_json()  # nobody's sentence
    assert team_insights(known, NOW, 30, min_people=2).false_friends == []
