"""Pick the storage at startup: Postgres when it answers, otherwise memory (and say so loudly)."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

import psycopg
from pydantic import ValidationError

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.local_file import LocalFileStorage
from mochi_backend.storage.port import NullStorage, Storage
from mochi_backend.storage.postgres import PostgresStorage
from mochi_backend.storage.write_behind import WriteBehindStorage
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
class TeamStart:
    """The company's learning history as storage held it at startup (DECISIONS D-45)."""

    companies: list[Company] = field(default_factory=list)
    members: list[Member] = field(default_factory=list)
    records: list[SessionRecord] = field(default_factory=list)
    moments: list[WordMoment] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    reports: list[ConversationReport] = field(default_factory=list)

    @classmethod
    def read(cls, storage: Storage) -> "TeamStart":
        """Load the company tables. Example: `TeamStart.read(fake).moments` is a list."""
        return cls(
            storage.load_companies(),
            storage.load_members(),
            storage.load_records(),
            storage.load_moments(),
            storage.load_utterances(),
            storage.load_reports(),
        )


@dataclass(frozen=True)
class StorageStart:
    """The storage to use, its name, and everything it held at startup (read once, here)."""

    storage: Storage = field(default_factory=NullStorage)
    name: str = VOLATILE
    users: list[User] = field(default_factory=list)
    events: list[LearningEvent] = field(default_factory=list)
    voices: list[VoiceProfile] = field(default_factory=list)
    team: TeamStart = field(default_factory=TeamStart)

    @classmethod
    def read(cls, storage: Storage, name: str) -> "StorageStart":
        """Load everything `storage` holds. Example: `StorageStart.read(fake, "x")`."""
        people = (storage.load_users(), storage.load_events(), storage.load_voices())
        return cls(storage, name, *people, TeamStart.read(storage))

    def over(self, storage: Storage) -> "StorageStart":
        """The same start, writing through `storage` from now on (the write-behind wrapper)."""
        return replace(self, storage=storage)


@dataclass(frozen=True)
class Seed:
    """What must exist after startup: the demo people and their company (added when missing)."""

    users: list[User] = field(default_factory=list)
    company: Company | None = None
    members: list[Member] = field(default_factory=list)

    def into(self, storage: Storage) -> None:
        """Add what is missing. Example: `Seed(users).into(storage)`."""
        storage.seed_users(self.users)
        if self.company is not None:
            storage.seed_company(self.company, self.members)


def storage_for(
    database_url: str,
    logger: EventLogger,
    seed: Seed,
    local_path: str = "",
    opener: Opener = Opener(),  # noqa: B008 - frozen, shared on purpose
) -> StorageStart:
    """Postgres and what it holds, else a local file (fake mode), else memory only.

    A database that is unreachable, expired (a free Render database expires after 30 days) or holds
    something unreadable must not stop Mochi from starting: it tries `opener.attempts` times, then
    runs from memory and logs `storage_unavailable` at ERROR level. `seed` is added when missing.
    `DATABASE_URL` wins over `local_path`.
    Example: `storage_for("", logger, Seed()).name` is `"memory"`.
    """
    if database_url:
        return _first_working(lambda: _postgres(database_url, logger, seed, opener), logger, opener)
    if local_path:
        return _first_working(
            lambda: _file(Path(local_path), logger, seed), logger, Opener(attempts=1)
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


def _postgres(url: str, logger: EventLogger, seed: Seed, opener: Opener) -> StorageStart:
    postgres = opener.postgres(url, logger)
    postgres.prepare()
    return _opened(postgres, PERSISTENT, logger, seed)


def _file(path: Path, logger: EventLogger, seed: Seed) -> StorageStart:
    return _opened(LocalFileStorage(path, logger), LOCAL, logger, seed)


def _opened(storage: Storage, kind: str, logger: EventLogger, seed: Seed) -> StorageStart:
    """Seed, read everything once, then put the write-behind queue in front of the writes."""
    seed.into(storage)
    start = StorageStart.read(storage, kind)
    counts = {"words": len(start.events), "moments": len(start.team.moments)}
    logger.log("storage_ready", {"kind": kind, **counts})
    return start.over(WriteBehindStorage(storage, logger))
