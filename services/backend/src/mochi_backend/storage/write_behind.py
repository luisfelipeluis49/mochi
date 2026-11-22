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
from mochi_backend.storage.session_record import SessionRecord
from mochi_contracts import LearningEvent, User, VoiceProfile

CLEAR_KEY = "events:clear"


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
        """Worker thread: the writes that failed before go first; this one only if they all pass.

        A write that comes after a failed one waits behind it without trying, so an outage costs one
        timeout per write at most, and nothing is ever applied out of order.
        """
        if key == CLEAR_KEY:
            self._drop_pending_events()  # every one of them is older than this clear
        if self._retry_backlog() and self._attempt(key, write):
            return
        self._park(key, write)

    def _drop_pending_events(self) -> None:
        with self._lock:
            self._failed = {k: w for k, w in self._failed.items() if not k.startswith("event:")}

    def _retry_backlog(self) -> bool:
        """Try the failed writes oldest first; stop at the first that fails again."""
        with self._lock:
            waiting = list(self._failed.items())
        for key, write in waiting:
            if not self._attempt(key, write):
                return False
            with self._lock:
                self._failed.pop(key, None)
        return True

    def _attempt(self, key: str, write: Callable[[], None]) -> bool:
        try:
            write()
        except Exception as error:  # noqa: BLE001 - any driver error must stay off the turn path
            self._logger.log("storage_write_failed", {"what": key, "error": type(error).__name__})
            return False
        return True

    def _park(self, key: str, write: Callable[[], None]) -> None:
        """Keep a write for the next try. A reset goes to the end: it is newer than what waits."""
        with self._lock:
            if key == CLEAR_KEY:
                self._failed.pop(key, None)
            self._failed[key] = write

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

    def save_user(self, user: User) -> None:
        """Queue the write on the same worker as the events: a user row is always written before
        that user's first learning event, which references it (D-42)."""
        self._later(f"user:{user.user_id}", lambda: self._inner.save_user(user))

    def load_events(self) -> list[LearningEvent]:
        """Pass-through read."""
        return self._inner.load_events()

    def save_event(self, event: LearningEvent) -> None:
        """Queue the write."""
        self._later(f"event:{event.learning_event_id}", lambda: self._inner.save_event(event))

    def clear_events(self) -> None:
        """Queue the delete."""
        self._later(CLEAR_KEY, self._inner.clear_events)

    def load_voices(self) -> list[VoiceProfile]:
        """Pass-through read."""
        return self._inner.load_voices()

    def save_voice(self, voice: VoiceProfile) -> None:
        """Queue the write."""
        self._later(f"voice:{voice_key(voice.name)}", lambda: self._inner.save_voice(voice))

    def delete_voice(self, name: str) -> None:
        """Queue the delete."""
        self._later(f"voice:{voice_key(name)}", lambda: self._inner.delete_voice(name))

    def load_sessions(self) -> list[SessionRecord]:
        """Pass-through read."""
        return self._inner.load_sessions()

    def save_session(self, record: SessionRecord) -> None:
        """Queue the write (after the user's own row, which it references)."""
        self._later(f"session:{record.record_id}", lambda: self._inner.save_session(record))
