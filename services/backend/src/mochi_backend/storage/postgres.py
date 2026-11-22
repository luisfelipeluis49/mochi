"""Postgres through psycopg 3. One short connection per call: writes are rare and run off-loop."""

from collections.abc import Callable

import psycopg
from pydantic import ValidationError

from mochi_backend.platform.clock import parse_iso_z
from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage import schema
from mochi_backend.storage.port import voice_key
from mochi_backend.storage.session_record import SessionRecord
from mochi_contracts import Language, LearningEvent, User, VoiceProfile

CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 10_000  # a database that accepts the connection and then hangs


class PostgresStorage:
    """Implements `Storage`. Example: `PostgresStorage(url).prepare()` then `load_events()`."""

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

    def prepare(self) -> None:
        """Create the tables that are missing. Raises `psycopg.Error` when unreachable."""
        with self._connect() as connection:
            for statement in schema.CREATE_TABLES:
                connection.execute(statement)

    def load_users(self) -> list[User]:
        """Every user, oldest first."""
        with self._connect() as connection:
            rows = connection.execute(schema.SELECT_USERS).fetchall()
        return self._parsed("users", rows, _user)

    def seed_users(self, users: list[User]) -> None:
        """Insert the users that do not exist yet; an existing one is left as it is."""
        with self._connect() as connection:
            for user in users:
                connection.execute(schema.INSERT_USER, _user_params(user))

    def save_user(self, user: User) -> None:
        """Insert one user if missing (`ON CONFLICT DO NOTHING`)."""
        with self._connect() as connection:
            connection.execute(schema.INSERT_USER, _user_params(user))

    def load_events(self) -> list[LearningEvent]:
        """Every learning event in the order it was first saved."""
        with self._connect() as connection:
            rows = connection.execute(schema.SELECT_EVENTS).fetchall()
        return self._parsed("learning_events", rows, _event)

    def save_event(self, event: LearningEvent) -> None:
        """Insert or replace one event by id."""
        params = (
            event.learning_event_id,
            event.user_id,
            event.expression,
            event.learning_state.value,
            event.model_dump_json(),
        )
        with self._connect() as connection:
            connection.execute(schema.UPSERT_EVENT, params)

    def clear_events(self) -> None:
        """Delete all learning events."""
        with self._connect() as connection:
            connection.execute(schema.DELETE_EVENTS)

    def load_voices(self) -> list[VoiceProfile]:
        """Every learned voice, with its vector."""
        with self._connect() as connection:
            rows = connection.execute(schema.SELECT_VOICES).fetchall()
        return self._parsed("voices", rows, _voice)

    def _parsed[T](
        self, table: str, rows: list[tuple[object, ...]], parse: Callable[[tuple[object, ...]], T]
    ) -> list[T]:
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

    def save_voice(self, voice: VoiceProfile) -> None:
        """Insert or replace one voice by name."""
        params = (
            voice_key(voice.name),
            voice.name,
            voice.user_id,
            voice.language,
            voice.voiceprint,
            voice.saved,
        )
        with self._connect() as connection:
            connection.execute(schema.UPSERT_VOICE, params)

    def delete_voice(self, name: str) -> None:
        """Delete one voice and its vector."""
        with self._connect() as connection:
            connection.execute(schema.DELETE_VOICE, (voice_key(name),))

    def load_sessions(self) -> list[SessionRecord]:
        """Every session record, oldest first by `ended_at`."""
        with self._connect() as connection:
            rows = connection.execute(schema.SELECT_SESSIONS).fetchall()
        return self._parsed("session_records", rows, _session)

    def save_session(self, record: SessionRecord) -> None:
        """Insert one record; one already there by id is left as it is."""
        params = (
            record.record_id,
            record.user_id,
            record.session_id,
            parse_iso_z(record.started_at),
            parse_iso_z(record.ended_at),
            record.model_dump_json(),
        )
        with self._connect() as connection:
            connection.execute(schema.INSERT_SESSION, params)

    def unsaved_writes(self) -> int:
        """Writes are direct here (`WriteBehindStorage` queues them), so nothing is waiting."""
        return 0


def _event(row: tuple[object, ...]) -> LearningEvent:
    return LearningEvent.model_validate_json(str(row[1]))


def _session(row: tuple[object, ...]) -> SessionRecord:
    return SessionRecord.model_validate_json(str(row[1]))


def _user_params(user: User) -> tuple[str, str, list[str], str]:
    languages = [language.value for language in user.comfortable_languages]
    return (user.user_id, user.display_name, languages, user.target_language.value)


def _user(row: tuple[object, ...]) -> User:
    languages = row[2] if isinstance(row[2], list) else []
    return User(
        user_id=str(row[0]),
        display_name=str(row[1]),
        comfortable_languages=[Language(str(language)) for language in languages],
        target_language=Language(str(row[3])),
    )


def _voice(row: tuple[object, ...]) -> VoiceProfile:
    vector = row[3]
    return VoiceProfile.model_validate(
        {
            "name": row[0],
            "user_id": row[1],
            "language": row[2],
            "voiceprint": [float(x) for x in vector] if isinstance(vector, list) else None,
            "saved": row[4],
        }
    )
