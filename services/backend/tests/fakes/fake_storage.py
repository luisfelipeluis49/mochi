"""A `Storage` that keeps everything in lists and can be told to fail. No database."""

from mochi_backend.storage.port import voice_key
from mochi_contracts import LearningEvent, User, VoiceProfile


class FakeStorage:
    """Implements `Storage`. Set `broken` to make every call raise, like a database that is down."""

    def __init__(self, users: list[User] | None = None) -> None:
        self.users: list[User] = list(users or [])
        self.events: dict[str, LearningEvent] = {}
        self.voices: dict[str, VoiceProfile] = {}
        self.calls: list[str] = []
        self.broken = False

    def _enter(self, call: str) -> None:
        self.calls.append(call)
        if self.broken:
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

    def load_events(self) -> list[LearningEvent]:
        """Events in the order first saved."""
        self._enter("load_events")
        return list(self.events.values())

    def save_event(self, event: LearningEvent) -> None:
        """Create or replace by id (a replaced event keeps its place)."""
        self._enter("save_event")
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
