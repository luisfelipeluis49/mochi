"""Durable storage: restore on start, write-behind, fallback to memory, voices, settings."""

import pytest

from mochi_backend.gateway.roster import DEMO_USERS, Roster
from mochi_backend.gateway.voice_directory import (
    InvalidVoiceprintError,
    VoiceDirectory,
    check_voiceprint,
)
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.settings import SettingsError, load_settings
from mochi_backend.storage.event_log import StorageEventSink
from mochi_backend.storage.factory import Opener, Seed, storage_for
from mochi_backend.storage.port import NullStorage, voice_key
from mochi_backend.storage.postgres import PostgresStorage
from mochi_backend.storage.postgres import _event as _event_row
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import (
    Language,
    LearningEvent,
    LearningState,
    Reason,
    StateChange,
    VoiceprintUpload,
    VoiceProfile,
)
from tests.fakes.fake_postgres import ReadFailsPostgres
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.fake_storage import FakeStorage


def _event(event_id: str, user: str | None = "ana", word: str = "postpone") -> LearningEvent:
    at = "2026-11-21T15:00:00.000Z"
    return LearningEvent(
        learning_event_id=event_id,
        user_id=user,
        target_language=Language.EN,
        expression=word,
        meaning="adiar",
        detection_signal=Reason.CODE_SWITCH,
        hint_id=None,
        learning_state=LearningState.DISCOVERED,
        state_history=[StateChange(learning_state=LearningState.DISCOVERED, at=at)],
    )


def test_words_saved_before_a_restart_come_back_newest_first() -> None:
    kept = FakeStorage()
    first = MemoryStore(sink=StorageEventSink(kept))
    first.apply([_event("a", word="postpone"), _event("b", word="umbrella")])
    second = MemoryStore(kept.load_events(), StorageEventSink(kept))
    assert [e.expression for e in second.words_for("ana")] == ["umbrella", "postpone"]


def test_an_updated_word_is_written_again_and_keeps_its_place() -> None:
    kept = FakeStorage()
    store = MemoryStore(sink=StorageEventSink(kept))
    store.apply([_event("a"), _event("b")])
    store.apply([_event("a", word="delay")])
    assert [e.expression for e in kept.load_events()] == ["delay", "postpone"]


def test_reset_clears_the_durable_copy_too() -> None:
    kept = FakeStorage()
    store = MemoryStore(sink=StorageEventSink(kept))
    store.apply([_event("a")])
    store.reset()
    assert kept.events == {} and store.words_for("ana") == []


def test_write_behind_runs_writes_in_order_and_reads_pass_through() -> None:
    inner, logger = FakeStorage(), FakeEventLogger()
    behind = WriteBehindStorage(inner, logger)
    behind.save_event(_event("a"))
    behind.clear_events()
    behind.save_event(_event("b"))
    behind.flush()
    assert inner.calls == ["save_event", "clear_events", "save_event"]
    assert [e.learning_event_id for e in behind.load_events()] == ["b"]


def test_a_failed_write_is_logged_and_never_raised() -> None:
    inner, logger = FakeStorage(), FakeEventLogger()
    inner.broken = True
    behind = WriteBehindStorage(inner, logger)
    behind.save_event(_event("a"))
    behind.flush()
    assert logger.lines == [
        ("storage_write_failed", {"what": "event:a", "error": "ConnectionError"})
    ]


NO_WAIT = Opener(attempts=3, pause=lambda _seconds: None)


def test_without_a_database_url_storage_is_memory_only() -> None:
    logger = FakeEventLogger()
    start = storage_for("", logger, Seed(DEMO_USERS))
    assert isinstance(start.storage, NullStorage) and start.name == "memory"
    assert logger.names() == ["storage_memory_only"]


def test_an_unreachable_database_falls_back_to_memory_and_says_so() -> None:
    logger = FakeEventLogger()
    start = storage_for("postgresql://u:p@127.0.0.1:1/none", logger, Seed(DEMO_USERS), "", NO_WAIT)
    assert isinstance(start.storage, NullStorage) and start.name == "memory"
    assert logger.names() == ["storage_unavailable"] * 3 + ["storage_fallback"]
    assert "127.0.0.1" not in repr(logger.lines) and "p@" not in repr(logger.lines)


def test_database_url_must_be_postgres_and_is_masked_in_errors() -> None:
    assert load_settings({"MOCHI_AGORA_MODE": "fake"}).database_url == ""
    with pytest.raises(SettingsError) as raised:
        load_settings({"MOCHI_AGORA_MODE": "fake", "DATABASE_URL": "mysql://u:secret@h/db"})
    assert "secret" not in str(raised.value) and "DATABASE_URL=***" in str(raised.value)


def _directory(storage: FakeStorage | None = None) -> tuple[VoiceDirectory, FakeStorage]:
    kept = storage or FakeStorage()
    return VoiceDirectory(kept, kept.load_voices(), Roster(DEMO_USERS)), kept


def test_a_voice_name_is_linked_to_its_user_in_any_case() -> None:
    directory, _ = _directory()
    assert directory.owner_of("ANA") == "ana" and directory.owner_of(" ben ") == "ben"
    assert directory.owner_of("Carla") is None
    assert voice_key(" Ana ") == "ana"


def test_linking_a_voice_again_keeps_its_vector() -> None:
    directory, kept = _directory()
    directory.store_vector("Ana", VoiceprintUpload(language="pt", voiceprint=[0.1, 0.2], saved="x"))
    linked = directory.link("ana", "en")
    assert linked.voiceprint == [0.1, 0.2] and linked.language == "en" and linked.user_id == "ana"
    assert kept.voices["ana"].voiceprint == [0.1, 0.2]


@pytest.mark.parametrize("vector", [[], [float("nan")], [float("inf")], [0.0] * 1025])
def test_a_bad_voiceprint_is_refused(vector: list[float]) -> None:
    with pytest.raises(InvalidVoiceprintError):
        check_voiceprint(vector)


def test_forgetting_a_voice_deletes_the_stored_copy() -> None:
    directory, kept = _directory()
    directory.link("Ana", "pt")
    assert directory.forget("ANA") is True and directory.forget("ana") is False
    assert kept.voices == {} and directory.all() == []


def test_voices_stored_before_a_restart_are_loaded() -> None:
    first, kept = _directory()
    first.store_vector("Ben", VoiceprintUpload(language="en", voiceprint=[0.5], saved=None))
    again, _ = _directory(kept)
    assert [v.name for v in again.all()] == ["Ben"] and again.all()[0].user_id == "ben"


def test_stored_rows_that_no_longer_fit_the_contract_are_skipped_not_fatal() -> None:
    logger = FakeEventLogger()
    storage = PostgresStorage("postgresql://unused", logger)
    good = _event("a").model_dump_json()
    stale = good.replace('"expression"', '"added_later":1,"expression"')
    rows: list[tuple[object, ...]] = [("old", stale), ("a", good), ("junk", "{not json")]
    kept = storage._parsed("learning_events", rows, _event_row)  # noqa: SLF001 - no database here
    assert [e.learning_event_id for e in kept] == ["a"]
    assert logger.lines == [
        ("storage_row_skipped", {"table": "learning_events", "key": "old"}),
        ("storage_row_skipped", {"table": "learning_events", "key": "junk"}),
    ]


def test_a_database_that_fails_while_loading_does_not_stop_startup() -> None:
    logger = FakeEventLogger()
    start = storage_for(
        "postgresql://unused", logger, Seed(DEMO_USERS), "", Opener(ReadFailsPostgres, 1)
    )
    assert start.name == "memory"
    assert logger.names() == ["storage_unavailable", "storage_fallback"]


def test_startup_waits_between_attempts_for_a_database_that_is_waking_up() -> None:
    pauses: list[float] = []
    opener = Opener(ReadFailsPostgres, attempts=3, pause=pauses.append, seconds_between=2.0)
    storage_for("postgresql://unused", FakeEventLogger(), Seed(DEMO_USERS), "", opener)
    assert pauses == [2.0, 2.0]


def _voice(name: str) -> VoiceProfile:
    return VoiceProfile(name=name, user_id="ana", language="pt", voiceprint=[0.1], saved=None)


def test_a_failed_write_is_tried_again_before_the_next_one() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    inner.broken = True
    behind.save_event(_event("a"))
    behind.flush()
    assert behind.unsaved_writes() == 1 and inner.events == {}
    inner.broken = False
    behind.save_event(_event("b"))
    behind.flush()
    assert list(inner.events) == ["a", "b"] and behind.unsaved_writes() == 0


def test_a_retried_save_never_brings_back_a_voice_that_was_forgotten() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    inner.broken = True
    behind.save_voice(_voice("Ana"))
    behind.delete_voice("ana")  # the newer write for the same voice replaces the failed save
    behind.flush()
    inner.broken = False
    behind.save_voice(_voice("Ben"))
    behind.flush()
    assert list(inner.voices) == ["ben"]


def test_a_failed_reset_is_retried_in_order_with_the_saves_around_it() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    behind.save_event(_event("old"))
    behind.flush()
    inner.broken = True
    behind.clear_events()
    behind.flush()
    inner.broken = False
    behind.save_event(_event("new"))
    behind.flush()
    assert list(inner.events) == ["new"]


def test_a_reset_made_during_an_outage_wins_over_words_saved_before_it() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    behind.save_event(_event("old"))
    behind.flush()
    inner.broken = True
    behind.clear_events()
    behind.save_event(_event("b"))
    behind.clear_events()  # a second reset: "b" is older than it and must not survive
    behind.flush()
    assert behind.unsaved_writes() == 1  # only the reset waits
    inner.broken = False
    behind.save_event(_event("c"))
    behind.flush()
    assert list(inner.events) == ["c"] and behind.unsaved_writes() == 0


def test_during_an_outage_a_new_write_waits_without_another_attempt() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    inner.broken = True
    behind.save_event(_event("a"))
    behind.flush()
    inner.calls.clear()
    behind.save_event(_event("b"))
    behind.flush()
    assert inner.calls == ["save_event"]  # the retry of "a" failed; "b" was not even tried
    assert behind.unsaved_writes() == 2
