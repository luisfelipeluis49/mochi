"""Users and session records in every storage (D-42): round trips, order, and what a reset keeps."""

from pathlib import Path

from mochi_backend.storage.factory import StorageStart, storage_for
from mochi_backend.storage.local_file import LocalFileStorage
from mochi_backend.storage.port import NullStorage
from mochi_backend.storage.postgres import PostgresStorage, _session
from mochi_backend.storage.session_record import SessionRecord
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import Language, User
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.fake_storage import FakeStorage
from tests.unit.test_storage import _event

LUIS = User(
    user_id="luis-3f9c1a",
    display_name="Luís",
    comfortable_languages=[Language.PT_BR],
    target_language=Language.EN,
)


def _record(record_id: str = "rec_1", user: str = "luis-3f9c1a") -> SessionRecord:
    return SessionRecord(
        record_id=record_id,
        session_id="w-1a2b3c4d",
        user_id=user,
        started_at="2026-11-21T10:00:00.000Z",
        ended_at="2026-11-21T10:12:30.000Z",
        minutes=12.5,
        hint_count=3,
        learning_event_ids=["learn_002", "learn_005"],
    )


def test_the_local_file_keeps_users_and_records_across_a_restart_and_a_reset(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mochi.json"
    first = LocalFileStorage(path, FakeEventLogger())
    first.save_user(LUIS)
    first.save_user(LUIS.model_copy(update={"display_name": "Other"}))  # never overwrites
    first.save_session(_record())
    first.save_session(_record())  # written once
    first.save_event(_event("learn_002", user="luis-3f9c1a"))
    first.clear_events()
    again = LocalFileStorage(path, FakeEventLogger())
    assert again.load_sessions() == [_record()]
    assert again.load_users() == [LUIS] and again.load_events() == []


def test_an_old_file_without_sessions_still_loads(tmp_path: Path) -> None:
    path = tmp_path / "mochi.json"
    path.write_text('{"users": [], "events": [], "voices": []}')
    assert LocalFileStorage(path, FakeEventLogger()).load_sessions() == []


def test_startup_reads_the_records_and_seeds_the_guest(tmp_path: Path) -> None:
    path = tmp_path / "mochi.json"
    LocalFileStorage(path, FakeEventLogger()).save_session(_record())
    guest = LUIS.model_copy(update={"user_id": "guest", "display_name": "Guest"})
    start = storage_for("", FakeEventLogger(), [guest], str(path))
    assert start.sessions == [_record()]
    assert [u.user_id for u in start.users] == ["guest"]


def test_storage_start_reads_records_from_any_storage() -> None:
    fake = FakeStorage()
    fake.save_session(_record())
    assert StorageStart.read(fake, "x").sessions == [_record()]
    assert StorageStart.read(NullStorage(), "memory").sessions == []


def test_null_storage_accepts_users_and_records_and_keeps_nothing() -> None:
    null = NullStorage()
    null.save_user(LUIS)
    null.save_session(_record())
    assert null.load_sessions() == [] and null.load_users() == []


def test_a_user_row_is_written_before_their_first_word_even_after_a_failure() -> None:
    inner = FakeStorage()
    inner.foreign_keys, inner.failing = True, {"save_user"}
    behind = WriteBehindStorage(inner, FakeEventLogger())
    behind.save_user(LUIS)
    behind.save_event(_event("learn_002", user="luis-3f9c1a"))
    behind.flush()
    assert inner.events == {} and behind.unsaved_writes() == 2  # the word waits behind its user
    assert inner.calls.count("save_event") == 0
    inner.failing = set()
    behind.save_session(_record())
    behind.flush()
    assert inner.users == [LUIS] and list(inner.events) == ["learn_002"]
    assert inner.sessions == [_record()] and behind.unsaved_writes() == 0
    assert inner.calls[-3:] == ["save_user", "save_event", "save_session"]


def test_a_reset_during_an_outage_keeps_the_waiting_user_and_record() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    inner.broken = True
    behind.save_user(LUIS)
    behind.save_session(_record())
    behind.clear_events()
    behind.flush()
    inner.broken = False
    behind.save_event(_event("new"))
    behind.flush()
    assert inner.users == [LUIS] and inner.sessions == [_record()]
    assert list(inner.events) == ["new"]


def test_write_behind_reads_records_through() -> None:
    inner = FakeStorage()
    inner.sessions.append(_record())
    assert WriteBehindStorage(inner, FakeEventLogger()).load_sessions() == [_record()]


def test_a_stored_record_that_no_longer_fits_is_skipped_not_fatal() -> None:
    logger = FakeEventLogger()
    storage = PostgresStorage("postgresql://unused", logger)
    good = _record().model_dump_json()
    rows: list[tuple[object, ...]] = [("rec_1", good), ("rec_x", '{"record_id": "rec_x"}')]
    kept = storage._parsed("session_records", rows, _session)  # noqa: SLF001 - no database here
    assert kept == [_record()]
    assert logger.lines == [("storage_row_skipped", {"table": "session_records", "key": "rec_x"})]
