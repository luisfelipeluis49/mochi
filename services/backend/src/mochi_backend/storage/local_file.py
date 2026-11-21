"""A `Storage` in one JSON file, for local work in fake mode (no database needed).

The file holds voiceprints, so it is created readable by its owner only. It is replaced
atomically, so a crash never leaves half a file. Not for production: a container's disk is wiped
on every deploy (see D-33).
"""

import json
import os
from pathlib import Path

from pydantic import BaseModel, ValidationError

from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.storage.port import voice_key
from mochi_contracts import LearningEvent, User, VoiceProfile


class LocalFileStorage:
    """Implements `Storage`. Example: `LocalFileStorage(Path("m.json"), logger).load_events()`."""

    def __init__(self, path: Path, logger: EventLogger) -> None:
        self._path = path
        self._logger = logger
        self._users: dict[str, User] = {}
        self._events: dict[str, LearningEvent] = {}
        self._voices: dict[str, VoiceProfile] = {}
        self._read()

    def _read(self) -> None:
        """Load the file if there is one. Raises `ValueError`/`OSError` when it is unreadable."""
        if not self._path.exists():
            return
        saved = json.loads(self._path.read_text())
        self._users = {u.user_id: u for u in self._rows("users", saved, User)}
        self._events = {e.learning_event_id: e for e in self._rows("events", saved, LearningEvent)}
        self._voices = {voice_key(v.name): v for v in self._rows("voices", saved, VoiceProfile)}

    def _rows[T: BaseModel](
        self, table: str, saved: dict[str, list[object]], model: type[T]
    ) -> list[T]:
        kept: list[T] = []
        for row in saved.get(table, []):
            try:
                kept.append(model.model_validate(row))
            except ValidationError:
                self._logger.log("storage_row_skipped", {"table": table, "file": self._path.name})
        return kept

    def _write(self) -> None:
        text = json.dumps(
            {
                "users": [u.model_dump(mode="json") for u in self._users.values()],
                "events": [e.model_dump(mode="json") for e in self._events.values()],
                "voices": [v.model_dump(mode="json") for v in self._voices.values()],
            }
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(text)
        os.replace(temporary, self._path)

    def load_users(self) -> list[User]:
        """Every stored user."""
        return list(self._users.values())

    def seed_users(self, users: list[User]) -> None:
        """Add the users that are missing."""
        self._users |= {u.user_id: u for u in users if u.user_id not in self._users}
        self._write()

    def load_events(self) -> list[LearningEvent]:
        """Events in the order first saved."""
        return list(self._events.values())

    def save_event(self, event: LearningEvent) -> None:
        """Create or replace by id (a replaced event keeps its place)."""
        self._events[event.learning_event_id] = event
        self._write()

    def clear_events(self) -> None:
        """Delete every event."""
        self._events.clear()
        self._write()

    def load_voices(self) -> list[VoiceProfile]:
        """Every stored voice."""
        return list(self._voices.values())

    def save_voice(self, voice: VoiceProfile) -> None:
        """Create or replace the voice with this name (any case)."""
        self._voices[voice_key(voice.name)] = voice
        self._write()

    def delete_voice(self, name: str) -> None:
        """Forget one voice."""
        self._voices.pop(voice_key(name), None)
        self._write()

    def unsaved_writes(self) -> int:
        """Writes are direct here, so nothing is ever waiting."""
        return 0
