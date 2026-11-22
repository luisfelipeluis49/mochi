"""Whose sentence is it: the device's stretches of speech matched to sentences by time (D-46)."""

from datetime import timedelta

from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS
from mochi_backend.platform.clock import iso_z
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.storage.factory import TeamStart
from mochi_backend.team.journal import SessionJournal
from mochi_backend.team.ledger import TeamLedger
from mochi_backend.team.timeline import ARRIVAL_LAG, Phrase, SpeakerTimeline, Verdict
from mochi_contracts import SessionMode, Turn
from tests.fakes.fake_clock import START, FakeClock
from tests.fakes.fake_storage import FakeStorage


def at(seconds: float) -> object:
    return START + timedelta(seconds=seconds)


def _timeline(*heard: tuple[str | None, float, float]) -> SpeakerTimeline:
    timeline = SpeakerTimeline()
    for who, seconds, ended in heard:
        timeline.add(Phrase(who, seconds, START + timedelta(seconds=ended)))
    return timeline


def _between(timeline: SpeakerTimeline, after: float, until: float) -> Verdict:
    return timeline.between(START + timedelta(seconds=after), START + timedelta(seconds=until))


def test_the_person_who_spoke_most_in_the_window_said_the_sentence() -> None:
    timeline = _timeline(("ana", 2.4, 3.0), ("ben", 0.4, 3.5), ("ben", 3.0, 9.0))
    assert _between(timeline, 0, 4) == Verdict(heard=True, user_id="ana")
    assert _between(timeline, 4, 10) == Verdict(heard=True, user_id="ben")
    assert _between(timeline, 3.0, 3.5).user_id == "ben"  # after is exclusive, until inclusive


def test_two_people_sharing_a_sentence_is_nobodys() -> None:
    timeline = _timeline(("ana", 1.0, 2.0), ("ben", 1.0, 3.0))
    assert _between(timeline, 0, 4) == Verdict(heard=True, user_id=None)


def test_unclear_speech_does_not_outvote_a_name_but_a_stranger_does() -> None:
    same_person = _timeline(("ana", 0.8, 1.0), (None, 0.5, 2.0))  # named early, then "not sure"
    assert _between(same_person, 0, 3).user_id == "ana"
    mostly_a_stranger = _timeline(("ana", 0.8, 1.0), (None, 3.0, 4.0))
    assert _between(mostly_a_stranger, 0, 5) == Verdict(heard=True, user_id=None)
    only_a_stranger = _timeline((None, 2.0, 1.0))
    assert _between(only_a_stranger, 0, 2) == Verdict(heard=True, user_id=None)


def test_a_time_the_device_said_nothing_about_is_not_heard() -> None:
    assert _between(_timeline(("ana", 2.0, 1.0)), 5, 9) == Verdict(heard=False, user_id=None)
    assert len(_timeline()) == 0 and len(_timeline(("ana", 1.0, 1.0))) == 1


def _journal() -> tuple[SessionJournal, TeamLedger, FakeClock]:
    clock = FakeClock()
    ledger = TeamLedger(FakeStorage(), TeamStart(), DEMO_COMPANY, DEMO_MEMBERS)
    journal = SessionJournal(ledger, clock, SequentialIdGenerator(), "demo")
    journal.begin("demo", SessionMode.MEETING, ["ana", "ben"])
    return journal, ledger, clock


def _turn(name: str, text: str, seconds: float, speaker: str | None) -> Turn:
    stamp = iso_z(START + timedelta(seconds=seconds))
    return Turn(segment_id=name, text=text, received_at=stamp, speaker_user_id=speaker)


def test_a_sentence_is_given_to_whoever_the_device_heard_since_the_one_before() -> None:
    journal, ledger, _ = _journal()
    journal.phrase("ana", 2.0, START + timedelta(seconds=3))
    arrives = START + timedelta(seconds=4)
    assert journal.speaker_of(arrives, sticky="ben") == "ana"  # the stretch, not the old name
    journal.heard(_turn("s1", "I need to adiar it", 4, "ana"))
    journal.phrase("ben", 1.5, START + timedelta(seconds=6))
    assert journal.speaker_of(START + timedelta(seconds=7), sticky=None) == "ben"
    journal.heard(_turn("s2", "Why is that", 7, "ben"))
    # nothing new was heard: the next sentence is nobody's, not Ben's again
    assert journal.speaker_of(START + timedelta(seconds=12), sticky="ben") is None
    assert [(u.text, u.user_id) for u in journal.transcript()] == [
        ("I need to adiar it", "ana"),
        ("Why is that", "ben"),
    ]
    assert [u.utterance_id for u in ledger.utterances_by("ana")] == ["s1"]


def test_a_stretch_that_ended_just_before_the_sentence_arrived_is_the_next_ones() -> None:
    journal, _, _ = _journal()
    arrives = START + timedelta(seconds=5)
    journal.phrase("ana", 2.0, arrives - ARRIVAL_LAG)  # exactly at the edge: still this sentence
    journal.phrase("ben", 2.0, arrives - ARRIVAL_LAG + timedelta(milliseconds=50))
    assert journal.speaker_of(arrives, sticky=None) == "ana"


def test_a_device_that_reports_no_stretches_keeps_the_last_named_speaker() -> None:
    journal, _, _ = _journal()
    assert journal.speaker_of(START + timedelta(seconds=4), sticky="ben") == "ben"
    assert journal.speaker_of(START + timedelta(seconds=4), sticky=None) is None


def test_a_report_that_came_after_its_sentence_is_counted_when_the_session_ends() -> None:
    journal, ledger, clock = _journal()
    journal.phrase("ben", 1.0, START + timedelta(seconds=1))
    journal.heard(_turn("s1", "Good morning", 2, "ben"))
    # Ana's sentence arrives before the device's report of her stretch does: nobody's for now
    assert journal.speaker_of(START + timedelta(seconds=6), sticky=None) is None
    journal.heard(_turn("s2", "I forgot my guarda-chuva", 6, None))
    journal.phrase("ana", 2.5, START + timedelta(seconds=5))  # the late report
    assert [u.user_id for u in journal.transcript()] == ["ben", None]
    clock.advance(60)
    journal.end()
    [record] = ledger.records_of("demo")
    assert [u.user_id for u in ledger.utterances_in(record.record_id)] == ["ben", "ana"]
    assert sorted((s.user_id or "", s.turns, s.words) for s in record.speaking) == [
        ("ana", 1, 4),
        ("ben", 1, 2),
    ]
    assert journal.transcript() == []  # no session is open any more


def test_nothing_is_kept_or_heard_outside_a_session() -> None:
    journal, ledger, _ = _journal()
    journal.end()
    journal.phrase("ana", 2.0, START)
    journal.heard(_turn("s1", "said after the meeting", 1, "ana"))
    assert ledger.utterances_by("ana") == []
    journal.begin("demo", SessionMode.MEETING, ["ana"])
    assert journal.speaker_of(START + timedelta(seconds=9), sticky="ben") == "ben"  # a fresh start
