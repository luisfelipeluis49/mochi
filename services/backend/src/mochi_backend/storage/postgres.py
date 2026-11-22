"""Postgres through psycopg 3. One short connection per call: writes are rare and run off-loop."""

from mochi_backend.platform.clock import parse_iso_z
from mochi_backend.storage import schema
from mochi_backend.storage.port import voice_key
from mochi_backend.storage.postgres_team import PostgresTeamTables
from mochi_backend.storage.session_record import SessionRecord as WebSessionRecord
from mochi_contracts import Language, LearningEvent, User, VoiceProfile


class PostgresStorage(PostgresTeamTables):
    """Implements `Storage`. Example: `PostgresStorage(url).prepare()` then `load_events()`."""

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
                languages = [language.value for language in user.comfortable_languages]
                params = (user.user_id, user.display_name, languages, user.target_language.value)
                connection.execute(schema.INSERT_USER, params)

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

    def load_sessions(self) -> list[WebSessionRecord]:
        """Every web session record, oldest first by `ended_at`."""
        with self._connect() as connection:
            rows = connection.execute(schema.SELECT_SESSIONS).fetchall()
        return self._parsed("session_records", rows, _session)

    def save_session(self, record: WebSessionRecord) -> None:
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

    def load_voices(self) -> list[VoiceProfile]:
        """Every learned voice, with its vector."""
        with self._connect() as connection:
            rows = connection.execute(schema.SELECT_VOICES).fetchall()
        return self._parsed("voices", rows, _voice)

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

    def unsaved_writes(self) -> int:
        """Writes are direct here (`WriteBehindStorage` queues them), so nothing is waiting."""
        return 0


def _session(row: tuple[object, ...]) -> WebSessionRecord:
    return WebSessionRecord.model_validate_json(str(row[1]))


def _event(row: tuple[object, ...]) -> LearningEvent:
    return LearningEvent.model_validate_json(str(row[1]))


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
