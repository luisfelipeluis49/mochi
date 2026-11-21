"""Pick the storage at startup: Postgres when it answers, otherwise memory (and say so loudly)."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from pydantic import ValidationError

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.local_file import LocalFileStorage
from mochi_backend.storage.port import NullStorage, Storage
from mochi_backend.storage.postgres import PostgresStorage
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import LearningEvent, User, VoiceProfile

PERSISTENT = "postgres"
LOCAL = "local_file"
VOLATILE = "memory"


@dataclass(frozen=True)
class Opener:
    """How to reach Postgres: the class to open it with, and how often to try (a free database
    that slept needs a moment). Tests pass a fake class and a `pause` that does not wait."""

    postgres: Callable[[str, EventLogger], PostgresStorage] = PostgresStorage
    attempts: int = 3
    pause: Callable[[float], None] = time.sleep
    seconds_between: float = 2.0


@dataclass(frozen=True)
class StorageStart:
    """The storage to use, its name, and everything it held at startup (read once, here)."""

    storage: Storage = field(default_factory=NullStorage)
    name: str = VOLATILE
    users: list[User] = field(default_factory=list)
    events: list[LearningEvent] = field(default_factory=list)
    voices: list[VoiceProfile] = field(default_factory=list)

    @classmethod
    def read(cls, storage: Storage, name: str) -> "StorageStart":
        """Load users, events and voices from `storage`. Example: `StorageStart.read(fake, "x")`."""
        return cls(
            storage, name, storage.load_users(), storage.load_events(), storage.load_voices()
        )


def storage_for(
    database_url: str,
    logger: EventLogger,
    users: list[User],
    local_path: str = "",
    opener: Opener = Opener(),  # noqa: B008 - frozen, shared on purpose
) -> StorageStart:
    """Postgres and what it holds, else a local file (fake mode), else memory only.

    A database that is unreachable, expired (a free Render database expires after 30 days) or holds
    something unreadable must not stop Mochi from starting: it tries `opener.attempts` times, then
    runs from memory and logs `storage_unavailable` at ERROR level. `users` are added when missing.
    `DATABASE_URL` wins over `local_path`.
    Example: `storage_for("", logger, []).name` is `"memory"`.
    """
    if database_url:
        return _first_working(
            lambda: _postgres(database_url, logger, users, opener), logger, opener
        )
    if local_path:
        return _first_working(
            lambda: _file(Path(local_path), logger, users), logger, Opener(attempts=1)
        )
    logger.log("storage_memory_only", {"reason": "DATABASE_URL is not set"})
    return StorageStart()


def _first_working(
    open_it: Callable[[], StorageStart], logger: EventLogger, opener: Opener
) -> StorageStart:
    for attempt in range(1, opener.attempts + 1):
        start = _attempt(open_it, logger, attempt)
        if start is not None:
            return start
        if attempt < opener.attempts:
            opener.pause(opener.seconds_between)
    logger.log("storage_fallback", {"fallback": VOLATILE})
    return StorageStart()


def _attempt(
    open_it: Callable[[], StorageStart], logger: EventLogger, number: int
) -> StorageStart | None:
    try:
        return open_it()
    except (psycopg.Error, OSError, ValidationError, ValueError) as error:
        logger.log("storage_unavailable", {"error": type(error).__name__, "attempt": number})
        return None


def _postgres(url: str, logger: EventLogger, users: list[User], opener: Opener) -> StorageStart:
    postgres = opener.postgres(url, logger)
    postgres.prepare()
    postgres.seed_users(users)
    start = StorageStart.read(postgres, PERSISTENT)
    logger.log("storage_ready", {"kind": PERSISTENT, "words": len(start.events)})
    return StorageStart(WriteBehindStorage(postgres, logger), PERSISTENT, *_rest(start))


def _file(path: Path, logger: EventLogger, users: list[User]) -> StorageStart:
    local = LocalFileStorage(path, logger)
    local.seed_users(users)
    start = StorageStart.read(local, LOCAL)
    logger.log("storage_ready", {"kind": LOCAL, "words": len(start.events)})
    return StorageStart(WriteBehindStorage(local, logger), LOCAL, *_rest(start))


def _rest(start: StorageStart) -> tuple[list[User], list[LearningEvent], list[VoiceProfile]]:
    return start.users, start.events, start.voices
