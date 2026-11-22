"""What every Postgres table class shares: the connection and row-by-row parsing."""

from collections.abc import Callable

import psycopg
from pydantic import ValidationError

from mochi_backend.platform.json_logging import EventLogger

CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 10_000  # a database that accepts the connection and then hangs
Row = tuple[object, ...]


class PostgresBase:
    """One short connection per call: writes are rare and run off-loop."""

    def __init__(self, url: str, logger: EventLogger) -> None:
        self._url = url
        self._logger = logger

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(
            self._url,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
            autocommit=True,
            options=f"-c statement_timeout={STATEMENT_TIMEOUT_MS}",
        )

    def _run(self, statement: str, params: Row = ()) -> None:
        with self._connect() as connection:
            connection.execute(statement, params)

    def _rows(self, statement: str) -> list[Row]:
        with self._connect() as connection:
            return connection.execute(statement).fetchall()

    def _parsed[T](self, table: str, rows: list[Row], parse: Callable[[Row], T]) -> list[T]:
        """Parse each row on its own: a stored row that no longer fits the contract is skipped.

        Contract models refuse unknown fields, so after a contract change an old row can fail to
        load; that must cost one word, not the whole startup. Logs the table and the row's key only.
        """
        kept: list[T] = []
        for row in rows:
            try:
                kept.append(parse(row))
            except (ValidationError, ValueError):
                key = "" if table == "voices" else str(row[0])[:60]  # a voice name is personal
                self._logger.log("storage_row_skipped", {"table": table, "key": key})
        return kept
