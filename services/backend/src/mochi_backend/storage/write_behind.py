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
from mochi_contracts import (
    Company,
    ConversationReport,
    LearningEvent,
    Member,
    SessionRecord,
    User,
    Utterance,
    VoiceProfile,
    WordMoment,
)

CLEAR_KEY = "events:clear"
HISTORY_CLEAR_KEY = "history:clear"
HISTORY_PREFIXES = ("record:", "moment:", "utterance:", "report:")


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
            self._drop_pending(("event:",))  # every one of them is older than this clear
        if key == HISTORY_CLEAR_KEY:
            self._drop_pending(HISTORY_PREFIXES)
        if self._retry_backlog() and self._attempt(key, write):
            return
        self._park(key, write)

    def _drop_pending(self, prefixes: tuple[str, ...]) -> None:
        with self._lock:
            self._failed = {k: w for k, w in self._failed.items() if not k.startswith(prefixes)}

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
            if key in (CLEAR_KEY, HISTORY_CLEAR_KEY):
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

    def save_user(self, user: User) -> None:
        """Queue the write."""
        self._later(f"user:{user.user_id}", lambda: self._inner.save_user(user))

    def load_companies(self) -> list[Company]:
        """Pass-through read."""
        return self._inner.load_companies()

    def load_members(self) -> list[Member]:
        """Pass-through read."""
        return self._inner.load_members()

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Pass-through: runs once at startup, before any turn."""
        self._inner.seed_company(company, members)

    def save_member(self, member: Member) -> None:
        """Queue the write (after the user's own, which was queued before it)."""
        key = f"member:{member.company_id}:{member.user_id}"
        self._later(key, lambda: self._inner.save_member(member))

    def load_records(self) -> list[SessionRecord]:
        """Pass-through read."""
        return self._inner.load_records()

    def save_record(self, record: SessionRecord) -> None:
        """Queue the write."""
        self._later(f"record:{record.record_id}", lambda: self._inner.save_record(record))

    def load_moments(self) -> list[WordMoment]:
        """Pass-through read."""
        return self._inner.load_moments()

    def save_moment(self, moment: WordMoment) -> None:
        """Queue the write."""
        self._later(f"moment:{moment.moment_id}", lambda: self._inner.save_moment(moment))

    def load_utterances(self) -> list[Utterance]:
        """Pass-through read."""
        return self._inner.load_utterances()

    def save_utterance(self, utterance: Utterance) -> None:
        """Queue the write."""
        key = f"utterance:{utterance.utterance_id}"
        self._later(key, lambda: self._inner.save_utterance(utterance))

    def load_reports(self) -> list[ConversationReport]:
        """Pass-through read."""
        return self._inner.load_reports()

    def save_report(self, report: ConversationReport) -> None:
        """Queue the write."""
        self._later(f"report:{report.report_id}", lambda: self._inner.save_report(report))

    def clear_history(self) -> None:
        """Queue the delete."""
        self._later(HISTORY_CLEAR_KEY, self._inner.clear_history)
