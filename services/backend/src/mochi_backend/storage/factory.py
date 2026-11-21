"""Pick the storage at startup: Postgres when it answers, otherwise memory (and say so loudly)."""

from collections.abc import Callable
from dataclasses import dataclass, field

import psycopg
from pydantic import ValidationError

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.port import NullStorage, Storage
from mochi_backend.storage.postgres import PostgresStorage
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import LearningEvent, User, VoiceProfile

PERSISTENT = "postgres"
VOLATILE = "memory"


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
    open_postgres: Callable[[str, EventLogger], PostgresStorage] = PostgresStorage,
) -> StorageStart:
    """Postgres and what it holds, or memory only.

    A database that is unreachable, expired (a free Render database expires after 30 days) or holds
    something unreadable must not stop Mochi from starting: it runs from memory and logs
    `storage_unavailable` at ERROR level. `users` are added to the table when missing.
    `open_postgres` is the seam for tests.
    Example: `storage_for("", logger, []).name` is `"memory"`.
    """
    if not database_url:
        logger.log("storage_memory_only", {"reason": "DATABASE_URL is not set"})
        return StorageStart()
    try:
        postgres = open_postgres(database_url, logger)
        postgres.prepare()
        postgres.seed_users(users)
        start = StorageStart.read(postgres, PERSISTENT)
    except (psycopg.Error, OSError, ValidationError, ValueError) as error:
        logger.log("storage_unavailable", {"error": type(error).__name__, "fallback": VOLATILE})
        return StorageStart()
    logger.log("storage_ready", {"kind": PERSISTENT, "words": len(start.events)})
    return StorageStart(WriteBehindStorage(postgres, logger), PERSISTENT, *_rest(start))


def _rest(start: StorageStart) -> tuple[list[User], list[LearningEvent], list[VoiceProfile]]:
    return start.users, start.events, start.voices
