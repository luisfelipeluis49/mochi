"""The journal writes a session into the ledger: when, who spoke, who needed which word."""

from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS, DEMO_USERS
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.storage.factory import TeamStart
from mochi_backend.team.journal import SessionJournal
from mochi_backend.team.ledger import TeamLedger
from mochi_contracts import Member, MemberRole, SessionMode
from tests.factories import make_hint, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_storage import FakeStorage


def _journal() -> tuple[SessionJournal, TeamLedger, FakeStorage, FakeClock]:
    storage, clock = FakeStorage(), FakeClock()
    ledger = TeamLedger(storage, TeamStart(), DEMO_COMPANY, DEMO_MEMBERS)
    journal = SessionJournal(ledger, clock, SequentialIdGenerator(), "demo")
    return journal, ledger, storage, clock


def test_a_session_is_recorded_from_start_to_stop_with_who_spoke() -> None:
    journal, ledger, storage, clock = _journal()
    journal.begin("demo", SessionMode.MEETING, ["ana", "ben"])
    [running] = ledger.records_of("demo")
    assert running.ended_at is None and running.participants == ["ana", "ben"]
    for number, speaker in enumerate(("ana", "ana", None)):
        said = make_turn("one two three", float(number))
        journal.heard(said.model_copy(update={"speaker_user_id": speaker}))
    clock.advance(600)
    journal.end()
    [closed] = ledger.records_of("demo")
    assert closed.record_id == running.record_id and closed.ended_at is not None
    assert [(s.user_id, s.turns, s.words) for s in closed.speaking] == [("ana", 2, 6), (None, 1, 3)]
    assert storage.calls.count("save_record") == 2  # once open, once closed
    journal.end()  # nothing open: nothing written
    assert storage.calls.count("save_record") == 2


def test_a_needed_word_is_kept_with_its_sentence_and_shown_again_is_still_one_moment() -> None:
    journal, ledger, _, clock = _journal()
    journal.begin("demo", SessionMode.MEETING, ["ana", "ben"])
    turn = make_turn("I need to adiar my meeting")
    first = journal.needed(make_hint(0), turn)
    assert first is not None and (first.user_id, first.expression) == ("ana", "postpone")
    assert first.heard == "I need to adiar my meeting" and first.record_id is not None
    clock.advance(20)
    assert journal.needed(make_hint(20), turn) is None  # "say it again?": the same moment
    clock.advance(120)
    assert journal.needed(make_hint(140), turn) is not None  # needed again, minutes later
    assert len(ledger.moments_of("demo")) == 2


def test_starting_again_closes_what_was_open_and_nothing_is_counted_between_sessions() -> None:
    journal, ledger, _, _ = _journal()
    journal.heard(make_turn("said before any session"))
    journal.begin("demo", SessionMode.MEETING, ["ana"])
    journal.begin("p-1", SessionMode.REVIEW, ["ana"])
    first, second = ledger.records_of("demo")
    assert first.ended_at is not None and first.speaking == []
    assert (second.mode, second.ended_at) == (SessionMode.REVIEW, None)


def test_the_ledger_knows_roles_and_forgets_history_but_not_people() -> None:
    journal, ledger, storage, _ = _journal()
    assert ledger.role_of("demo", "ana") is MemberRole.ADMIN
    assert ledger.role_of("demo", "ben") is MemberRole.MEMBER
    assert ledger.role_of("demo", "zed") is None and ledger.role_of("demo", None) is None
    assert ledger.company("demo") == DEMO_COMPANY and ledger.company("other") is None
    assert ledger.companies_of("ana") == ["demo"] and ledger.companies_of("zed") == []
    journal.begin("demo", SessionMode.MEETING, ["ana"])
    journal.needed(make_hint(0), make_turn("x"))
    ledger.clear_history()
    assert ledger.records_of("demo") == [] and ledger.moments_of("demo") == []
    assert len(ledger.members_of("demo")) == 2 and "clear_history" in storage.calls


def test_a_new_member_is_saved_after_the_person_they_refer_to() -> None:
    _, ledger, storage, _ = _journal()
    caio = DEMO_USERS[0].model_copy(update={"user_id": "caio", "display_name": "Caio"})
    joined = Member(company_id="demo", user_id="caio", role=MemberRole.MEMBER, team="Sales")
    ledger.keep_member(caio, joined)
    assert storage.calls[-2:] == ["save_user", "save_member"]
    assert ledger.members_of("demo")[-1] == joined


def test_what_storage_held_at_startup_wins_over_the_defaults() -> None:
    kept = Member(company_id="demo", user_id="ben", role=MemberRole.ADMIN)
    ledger = TeamLedger(FakeStorage(), TeamStart(members=[kept]), DEMO_COMPANY, DEMO_MEMBERS)
    assert ledger.role_of("demo", "ben") is MemberRole.ADMIN
    assert ledger.role_of("demo", "ana") is None  # storage is the truth once it holds members
