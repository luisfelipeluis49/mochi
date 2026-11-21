"""Durable storage: restore on start, write-behind, fallback to memory, voices, settings."""

import pytest

from mochi_backend.gateway.roster import DEMO_USERS
from mochi_backend.gateway.voice_directory import (
    InvalidVoiceprintError,
    VoiceDirectory,
    check_voiceprint,
)
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.settings import SettingsError, load_settings
from mochi_backend.storage.event_log import StorageEventSink
from mochi_backend.storage.factory import storage_for
from mochi_backend.storage.port import NullStorage, voice_key
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import (
    Language,
    LearningEvent,
    LearningState,
    Reason,
    StateChange,
    VoiceprintUpload,
)
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
        ("storage_write_failed", {"what": "save_event", "error": "ConnectionError"})
    ]


def test_without_a_database_url_storage_is_memory_only() -> None:
    logger = FakeEventLogger()
    storage, name = storage_for("", logger, DEMO_USERS)
    assert isinstance(storage, NullStorage) and name == "memory"
    assert logger.names() == ["storage_memory_only"]


def test_an_unreachable_database_falls_back_to_memory_and_says_so() -> None:
    logger = FakeEventLogger()
    storage, name = storage_for("postgresql://u:p@127.0.0.1:1/none", logger, DEMO_USERS)
    assert isinstance(storage, NullStorage) and name == "memory"
    assert logger.names() == ["storage_unavailable"]
    assert "127.0.0.1" not in repr(logger.lines) and "p@" not in repr(logger.lines)


def test_database_url_must_be_postgres_and_is_masked_in_errors() -> None:
    assert load_settings({"MOCHI_AGORA_MODE": "fake"}).database_url == ""
    with pytest.raises(SettingsError) as raised:
        load_settings({"MOCHI_AGORA_MODE": "fake", "DATABASE_URL": "mysql://u:secret@h/db"})
    assert "secret" not in str(raised.value) and "DATABASE_URL=***" in str(raised.value)


def _directory(storage: FakeStorage | None = None) -> tuple[VoiceDirectory, FakeStorage]:
    kept = storage or FakeStorage()
    return VoiceDirectory(kept, DEMO_USERS), kept


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
