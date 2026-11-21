"""Writes go to the database on a worker thread, so a slow or broken database never delays a turn.

Reads (startup only) go straight through. A failed write is logged and kept (the newest failed
write per record): the worker tries it again before the next write, always in the order the writes
were made, so a retried save can never undo a later delete. `unsaved_writes()` says how many are
still waiting, which `/readyz` reports.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.port import Storage, voice_key
from mochi_contracts import LearningEvent, User, VoiceProfile


class WriteBehindStorage:
    """Implements `Storage` over another `Storage`. One worker keeps the writes in order."""

    def __init__(self, inner: Storage, logger: EventLogger) -> None:
        self._inner = inner
        self._logger = logger
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mochi-storage")
        self._failed: dict[str, Callable[[], None]] = {}  # by record key, oldest first
        self._lock = Lock()

    def _later(self, key: str, write: Callable[[], None]) -> None:
        self._worker.submit(self._run, key, write)

    def _run(self, key: str, write: Callable[[], None]) -> None:
        """Worker thread: first the writes that failed before, then this one."""
        for old_key, old_write in self._snapshot_failed():
            self._try(old_key, old_write)
        self._try(key, write)

    def _snapshot_failed(self) -> list[tuple[str, Callable[[], None]]]:
        with self._lock:
            return list(self._failed.items())

    def _try(self, key: str, write: Callable[[], None]) -> None:
        try:
            write()
        except Exception as error:  # noqa: BLE001 - any driver error must stay off the turn path
            with self._lock:
                self._failed[key] = write  # a key that is already waiting keeps its place
            self._logger.log("storage_write_failed", {"what": key, "error": type(error).__name__})
        else:
            with self._lock:
                self._failed.pop(key, None)

    def unsaved_writes(self) -> int:
        """How many writes failed and are waiting for the next try. 0 means everything is saved."""
        with self._lock:
            return len(self._failed)

    def flush(self) -> None:
        """Wait until every write queued so far has run (tests, and a clean shutdown)."""
        self._worker.submit(lambda: None).result()

    def load_users(self) -> list[User]:
        """Pass-through read."""
        return self._inner.load_users()

    def seed_users(self, users: list[User]) -> None:
        """Pass-through: runs once at startup, before any turn."""
        self._inner.seed_users(users)

    def load_events(self) -> list[LearningEvent]:
        """Pass-through read."""
        return self._inner.load_events()

    def save_event(self, event: LearningEvent) -> None:
        """Queue the write."""
        self._later(f"event:{event.learning_event_id}", lambda: self._inner.save_event(event))

    def clear_events(self) -> None:
        """Queue the delete."""
        self._later("events:clear", self._inner.clear_events)

    def load_voices(self) -> list[VoiceProfile]:
        """Pass-through read."""
        return self._inner.load_voices()

    def save_voice(self, voice: VoiceProfile) -> None:
        """Queue the write."""
        self._later(f"voice:{voice_key(voice.name)}", lambda: self._inner.save_voice(voice))

    def delete_voice(self, name: str) -> None:
        """Queue the delete."""
        self._later(f"voice:{voice_key(name)}", lambda: self._inner.delete_voice(name))
