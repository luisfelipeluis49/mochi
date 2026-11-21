"""The real Postgres adapter. Runs only when MOCHI_TEST_DATABASE_URL points at a throwaway database.

Example: docker run -d --rm -p 55432:5432 -e POSTGRES_PASSWORD=t postgres:17, then
MOCHI_TEST_DATABASE_URL=postgresql://postgres:t@localhost:55432/postgres make test
"""

import os
from collections.abc import Iterator

import psycopg
import pytest

from mochi_backend.gateway.roster import DEMO_USERS
from mochi_backend.storage.postgres import PostgresStorage
from mochi_contracts import (
    Language,
    LearningEvent,
    LearningState,
    Reason,
    StateChange,
    VoiceProfile,
)

URL = os.environ.get("MOCHI_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="MOCHI_TEST_DATABASE_URL is not set")


@pytest.fixture
def storage() -> Iterator[PostgresStorage]:
    with psycopg.connect(URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS voices, learning_events, users")
    database = PostgresStorage(URL)
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
