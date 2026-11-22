"""The real Postgres adapter. Runs only when MOCHI_TEST_DATABASE_URL points at a throwaway database.

Example: docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=t postgres:17, then
MOCHI_TEST_DATABASE_URL=postgresql://postgres:t@localhost:55432/postgres make test
"""

import os
from collections.abc import Iterator

import psycopg
import pytest

from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS, DEMO_USERS
from mochi_backend.storage.postgres import PostgresStorage
from mochi_backend.storage.session_record import SessionRecord as WebSessionRecord
from mochi_contracts import (
    Language,
    LearningEvent,
    LearningState,
    Member,
    MemberRole,
    Reason,
    StateChange,
    User,
    Utterance,
    VoiceProfile,
)
from tests.fakes.fake_sender import FakeEventLogger
from tests.unit.test_speech_report import draft
from tests.unit.test_team_view import moment, record

URL = os.environ.get("MOCHI_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="MOCHI_TEST_DATABASE_URL is not set")


@pytest.fixture
def storage() -> Iterator[PostgresStorage]:
    with psycopg.connect(URL, autocommit=True) as connection:
        connection.execute(
            "DROP TABLE IF EXISTS conversation_reports, utterances, word_moments, "
            "company_sessions, company_members, companies, session_records, "
            "voices, learning_events, users"
        )
    database = PostgresStorage(URL, FakeEventLogger())
    database.prepare()
    database.seed_users(DEMO_USERS)
    yield database


def _event(event_id: str, word: str, user: str | None = "ana") -> LearningEvent:
    at = "2026-11-21T15:00:00.000Z"
    return LearningEvent(
        learning_event_id=event_id,
        user_id=user,
        target_language=Language.EN,
        expression=word,
        meaning=None,
        detection_signal=Reason.CODE_SWITCH,
        hint_id=None,
        learning_state=LearningState.DISCOVERED,
        state_history=[StateChange(learning_state=LearningState.DISCOVERED, at=at)],
    )


def test_prepare_is_repeatable_and_seeding_never_overwrites(storage: PostgresStorage) -> None:
    storage.prepare()
    with psycopg.connect(URL, autocommit=True) as connection:
        connection.execute("UPDATE users SET display_name = 'Aninha' WHERE user_id = 'ana'")
    storage.seed_users(DEMO_USERS)
    users = {u.user_id: u for u in storage.load_users()}
    assert users["ana"].display_name == "Aninha" and users["ben"].display_name == "Ben"
    assert users["ana"].comfortable_languages == [Language.PT_BR]


def test_events_round_trip_in_first_saved_order(storage: PostgresStorage) -> None:
    storage.save_event(_event("a", "postpone"))
    storage.save_event(_event("b", "umbrella"))
    storage.save_event(_event("a", "delay"))
    assert [e.expression for e in storage.load_events()] == ["delay", "umbrella"]
    assert storage.load_events()[0] == _event("a", "delay")


def test_an_event_with_no_user_is_stored_and_clear_keeps_users_and_voices(
    storage: PostgresStorage,
) -> None:
    storage.save_event(_event("x", "receipt", user=None))
    storage.save_voice(
        VoiceProfile(name="Ana", user_id="ana", language="pt", voiceprint=[0.5], saved=None)
    )
    assert storage.load_events()[0].user_id is None
    storage.clear_events()
    assert storage.load_events() == [] and len(storage.load_users()) == 2
    assert [v.name for v in storage.load_voices()] == ["Ana"]


def test_a_voice_keeps_its_vector_and_is_replaced_by_name_in_any_case(
    storage: PostgresStorage,
) -> None:
    vector = [0.1, -0.2, 0.3]
    storage.save_voice(
        VoiceProfile(name="Ana", user_id="ana", language="pt", voiceprint=vector, saved="s")
    )
    storage.save_voice(
        VoiceProfile(name="ANA", user_id="ana", language="en", voiceprint=vector, saved="s")
    )
    [voice] = storage.load_voices()
    assert (voice.name, voice.language, voice.voiceprint) == ("ANA", "en", vector)
    storage.delete_voice("ana")
    assert storage.load_voices() == []


def test_the_company_tables_round_trip_and_a_reset_keeps_the_people(
    storage: PostgresStorage,
) -> None:
    storage.seed_company(DEMO_COMPANY, DEMO_MEMBERS)
    storage.seed_company(DEMO_COMPANY, DEMO_MEMBERS)  # repeatable
    caio = DEMO_USERS[0].model_copy(update={"user_id": "caio", "display_name": "Caio"})
    storage.save_user(caio)
    storage.save_member(Member(company_id="demo", user_id="caio", role=MemberRole.MEMBER))
    storage.save_member(Member(company_id="demo", user_id="ben", role=MemberRole.ADMIN, team="Ops"))
    assert storage.load_companies() == [DEMO_COMPANY]
    roles = {m.user_id: (m.role, m.team) for m in storage.load_members()}
    assert roles["ben"] == (MemberRole.ADMIN, "Ops") and roles["caio"] == (MemberRole.MEMBER, None)
    open_record = record().model_copy(update={"ended_at": None})
    storage.save_record(open_record)
    storage.save_record(record())  # the same id, now ended
    storage.save_moment(moment("postpone", "ana"))
    storage.save_moment(moment("postpone", "ana"))  # the same id: kept once
    storage.save_moment(moment("umbrella", None))
    assert storage.load_records() == [record()]
    assert [m.expression for m in storage.load_moments()] == ["postpone", "umbrella"]
    said = Utterance(
        utterance_id="seg_1",
        company_id="demo",
        record_id=record().record_id,
        user_id=None,
        text="I need to adiar my meeting",
        at="2026-11-19T16:00:04.500Z",
    )
    storage.save_utterance(said)
    storage.save_utterance(said.model_copy(update={"user_id": "ana"}))  # its speaker became known
    assert [(u.text, u.user_id) for u in storage.load_utterances()] == [(said.text, "ana")]
    storage.clear_history()
    assert storage.load_records() == [] and storage.load_moments() == []
    assert storage.load_utterances() == [] and len(storage.load_members()) == 3


def _web_record(record_id: str, ended: str, user: str = "luis-3f9c1a") -> WebSessionRecord:
    return WebSessionRecord(
        record_id=record_id,
        session_id="w-1a2b3c4d",
        user_id=user,
        started_at="2026-11-21T10:00:00.000Z",
        ended_at=ended,
        minutes=12.5,
        hint_count=3,
        learning_event_ids=["learn_002"],
    )


def test_a_web_user_and_their_session_records_round_trip_and_survive_a_reset(
    storage: PostgresStorage,
) -> None:
    luis = User(
        user_id="luis-3f9c1a",
        display_name="Luís",
        comfortable_languages=[Language.PT_BR],
        target_language=Language.EN,
    )
    storage.save_user(luis)
    storage.save_event(_event("learn_002", "postpone", user="luis-3f9c1a"))
    storage.save_session(_web_record("rec_2", "2026-11-21T10:12:30.000Z"))
    storage.save_session(_web_record("rec_1", "2026-11-21T10:05:00.000Z"))
    storage.save_session(_web_record("rec_1", "2026-11-21T10:05:00.000Z"))  # written once
    storage.clear_events()
    storage.clear_history()  # the company's history goes; a person's web sessions stay
    assert [r.record_id for r in storage.load_sessions()] == ["rec_1", "rec_2"]
    assert storage.load_sessions()[1] == _web_record("rec_2", "2026-11-21T10:12:30.000Z")
    names = {u.user_id: u.display_name for u in storage.load_users()}
    assert names["luis-3f9c1a"] == "Luís"


def test_the_reports_table_takes_a_report_once_and_goes_with_the_history(
    storage: PostgresStorage,
) -> None:
    storage.seed_users(DEMO_USERS)
    storage.seed_company(DEMO_COMPANY, DEMO_MEMBERS)  # a report refers to its company and person
    report = draft()
    storage.save_report(report)
    storage.save_report(report.model_copy(update={"strengths": ["changed"]}))  # never rewritten
    assert storage.load_reports() == [report]
    storage.clear_history()
    assert storage.load_reports() == []
