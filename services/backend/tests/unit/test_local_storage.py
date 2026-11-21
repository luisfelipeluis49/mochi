"""The local file storage (fake mode), and the rules around choosing it."""

import stat
from pathlib import Path

import pytest

from mochi_backend.gateway.roster import DEMO_USERS
from mochi_backend.settings import SettingsError, load_settings
from mochi_backend.storage.factory import Opener, storage_for
from mochi_backend.storage.local_file import LocalFileStorage
from tests.fakes.fake_postgres import ReadFailsPostgres
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.fake_storage import FakeStorage
from tests.unit.test_storage import _event as event
from tests.unit.test_storage import _voice as voice


def test_words_and_voices_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "mochi.json"
    first = LocalFileStorage(path, FakeEventLogger())
    first.save_event(event("learn_1", "ana"))
    first.save_voice(voice("Ana"))
    second = LocalFileStorage(path, FakeEventLogger())
    assert [e.learning_event_id for e in second.load_events()] == ["learn_1"]
    assert [v.name for v in second.load_voices()] == ["Ana"]


def test_the_file_is_private_and_clear_and_forget_are_kept(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "mochi.json"
    store = LocalFileStorage(path, FakeEventLogger())
    store.save_event(event("learn_1", "ana"))
    store.save_voice(voice("Ana"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600  # it holds voiceprints
    store.clear_events()
    store.delete_voice(" ana ")
    again = LocalFileStorage(path, FakeEventLogger())
    assert again.load_events() == [] and again.load_voices() == []
    assert not path.with_suffix(".tmp").exists()


def test_a_row_that_no_longer_fits_is_skipped_not_fatal(tmp_path: Path) -> None:
    path = tmp_path / "mochi.json"
    path.write_text('{"events": [{"nonsense": 1}], "voices": []}')
    logger = FakeEventLogger()
    assert LocalFileStorage(path, logger).load_events() == []
    assert logger.names() == ["storage_row_skipped"]


def test_an_unreadable_file_means_memory_not_a_crash(tmp_path: Path) -> None:
    path = tmp_path / "mochi.json"
    path.write_text("{not json")
    start = storage_for("", FakeEventLogger(), DEMO_USERS, str(path))
    assert start.name == "memory"


def test_a_local_file_start_seeds_users_and_names_itself(tmp_path: Path) -> None:
    start = storage_for("", FakeEventLogger(), DEMO_USERS, str(tmp_path / "m.json"))
    assert start.name == "local_file" and [u.user_id for u in start.users] == ["ana", "ben"]


def test_the_database_wins_over_the_file(tmp_path: Path) -> None:
    opener = Opener(ReadFailsPostgres, attempts=1)
    start = storage_for("postgresql://x", FakeEventLogger(), [], str(tmp_path / "m.json"), opener)
    assert start.name == "memory"  # it tried Postgres, not the file
    assert not (tmp_path / "m.json").exists()


def test_the_file_is_refused_in_real_mode() -> None:
    real = {
        "MOCHI_AGORA_MODE": "real",
        "MOCHI_LOCAL_DATA": "x.json",
        "AGORA_APP_ID": "a",
        "AGORA_APP_CERTIFICATE": "c",
        "AGORA_REST_KEY": "k",
        "AGORA_REST_SECRET": "s",
        "MOCHI_TURN_KEY": "t",
        "MOCHI_DEVICE_KEY": "d",
        "MOCHI_PUBLIC_URL": "https://example.com",
    }
    with pytest.raises(SettingsError, match="MOCHI_LOCAL_DATA"):
        load_settings(real)
    assert load_settings({**real, "MOCHI_LOCAL_DATA": ""}).mochi_local_data == ""


def test_fake_mode_accepts_the_file() -> None:
    settings = load_settings({"MOCHI_AGORA_MODE": "fake", "MOCHI_LOCAL_DATA": "x.json"})
    assert settings.mochi_local_data == "x.json" and FakeStorage().unsaved_writes() == 0
