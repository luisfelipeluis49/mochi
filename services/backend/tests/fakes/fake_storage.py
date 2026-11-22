"""A `Storage` that keeps everything in lists and can be told to fail. No database."""

from mochi_backend.storage.port import voice_key
from mochi_backend.storage.session_record import SessionRecord
from mochi_contracts import LearningEvent, User, VoiceProfile


class FakeStorage:
    """Implements `Storage`. Set `broken` to make every call raise, like a database that is down."""

    def __init__(self, users: list[User] | None = None) -> None:
        self.users: list[User] = list(users or [])
        self.events: dict[str, LearningEvent] = {}
        self.voices: dict[str, VoiceProfile] = {}
        self.sessions: list[SessionRecord] = []
        self.calls: list[str] = []
        self.broken = False
        self.failing: set[str] = set()  # calls that fail on their own, e.g. {"save_user"}
        self.foreign_keys = (
            False  # True: an event for a user that is not stored fails, like Postgres
        )

    def _enter(self, call: str) -> None:
        self.calls.append(call)
        if self.broken or call in self.failing:
            raise ConnectionError(f"{call}: the fake database is down")

    def load_users(self) -> list[User]:
        """The stored users."""
        self._enter("load_users")
        return list(self.users)

    def seed_users(self, users: list[User]) -> None:
        """Add the users whose id is missing."""
        self._enter("seed_users")
        known = {user.user_id for user in self.users}
        self.users += [user for user in users if user.user_id not in known]

    def save_user(self, user: User) -> None:
        """Add the user if its id is missing (never a duplicate)."""
        self._enter("save_user")
        if all(known.user_id != user.user_id for known in self.users):
            self.users.append(user)

    def load_events(self) -> list[LearningEvent]:
        """Events in the order first saved."""
        self._enter("load_events")
        return list(self.events.values())

    def save_event(self, event: LearningEvent) -> None:
        """Create or replace by id (a replaced event keeps its place)."""
        self._enter("save_event")
        known = {user.user_id for user in self.users}
        if self.foreign_keys and event.user_id is not None and event.user_id not in known:
            raise ConnectionError(f"save_event: no user {event.user_id!r} (foreign key)")
        self.events[event.learning_event_id] = event

    def clear_events(self) -> None:
        """Delete all events."""
        self._enter("clear_events")
        self.events.clear()

    def load_voices(self) -> list[VoiceProfile]:
        """The stored voices."""
        self._enter("load_voices")
        return list(self.voices.values())

    def save_voice(self, voice: VoiceProfile) -> None:
        """Create or replace by name."""
        self._enter("save_voice")
        self.voices[voice_key(voice.name)] = voice

    def delete_voice(self, name: str) -> None:
        """Delete by name."""
        self._enter("delete_voice")
        self.voices.pop(voice_key(name), None)

    def load_sessions(self) -> list[SessionRecord]:
        """The stored session records, oldest first."""
        self._enter("load_sessions")
        return list(self.sessions)

    def save_session(self, record: SessionRecord) -> None:
        """Append a record."""
        self._enter("save_session")
        self.sessions.append(record)

    def unsaved_writes(self) -> int:
        """Nothing waits in a fake."""
        return 0
