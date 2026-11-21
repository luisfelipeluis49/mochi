"""Writes go to the database on a worker thread, so a slow or broken database never delays a turn.

Reads (startup only) go straight through. A failed write is logged and dropped: the word is still
in memory, and the next write for it carries the full record again.
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.port import Storage
from mochi_contracts import LearningEvent, User, VoiceProfile


class WriteBehindStorage:
    """Implements `Storage` over another `Storage`. One worker keeps the writes in order."""

    def __init__(self, inner: Storage, logger: EventLogger) -> None:
        self._inner = inner
        self._logger = logger
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mochi-storage")

    def _later(self, what: str, write: Callable[[], None]) -> None:
        self._worker.submit(self._guarded, what, write)

    def _guarded(self, what: str, write: Callable[[], None]) -> None:
        try:
            write()
        except Exception as error:  # noqa: BLE001 - any driver error must stay off the turn path
            self._logger.log("storage_write_failed", {"what": what, "error": type(error).__name__})

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
        self._later("save_event", lambda: self._inner.save_event(event))

    def clear_events(self) -> None:
        """Queue the delete."""
        self._later("clear_events", self._inner.clear_events)

    def load_voices(self) -> list[VoiceProfile]:
        """Pass-through read."""
        return self._inner.load_voices()

    def save_voice(self, voice: VoiceProfile) -> None:
        """Queue the write."""
        self._later("save_voice", lambda: self._inner.save_voice(voice))

    def delete_voice(self, name: str) -> None:
        """Queue the delete."""
        self._later("delete_voice", lambda: self._inner.delete_voice(name))
