"""Pick the storage at startup: Postgres when it answers, otherwise memory (and say so loudly)."""

import psycopg

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.port import NullStorage, Storage
from mochi_backend.storage.postgres import PostgresStorage
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import User

PERSISTENT = "postgres"
VOLATILE = "memory"


def storage_for(database_url: str, logger: EventLogger, users: list[User]) -> tuple[Storage, str]:
    """The storage to use and its name (`postgres` or `memory`).

    An unreachable or expired database (a free Render database expires after 30 days) must not stop
    Mochi from starting: it runs from memory and logs `storage_unavailable` at ERROR level.
    `users` are added to the table when missing. Example: `storage_for("", logger, [])` is
    `(NullStorage(), "memory")`.
    """
    if not database_url:
        logger.log("storage_memory_only", {"reason": "DATABASE_URL is not set"})
        return NullStorage(), VOLATILE
    postgres = PostgresStorage(database_url)
    try:
        postgres.prepare()
        postgres.seed_users(users)
    except (psycopg.Error, OSError) as error:
        logger.log("storage_unavailable", {"error": type(error).__name__, "fallback": VOLATILE})
        return NullStorage(), VOLATILE
    logger.log("storage_ready", {"kind": PERSISTENT})
    return WriteBehindStorage(postgres, logger), PERSISTENT
