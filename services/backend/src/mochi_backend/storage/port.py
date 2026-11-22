"""What the backend needs from a database. Postgres implements it; tests use a fake."""

from typing import Protocol

from mochi_backend.storage.session_record import SessionRecord
from mochi_contracts import LearningEvent, User, VoiceProfile


def voice_key(name: str) -> str:
    """The case-insensitive key of a voice name. Example: `voice_key(" Ana ")` is `"ana"`."""
    return name.strip().casefold()


class Storage(Protocol):
    """Durable copies of users, learning events, voices and session records. Reads happen once,
    at startup."""

    def load_users(self) -> list[User]:
        """Every known user (empty when nothing is stored)."""
        ...

    def seed_users(self, users: list[User]) -> None:
        """Add users that are missing; never overwrites one that exists."""
        ...

    def save_user(self, user: User) -> None:
        """Add one user if missing (a web user, D-42); an existing one is left as it is."""
        ...

    def load_events(self) -> list[LearningEvent]:
        """Every saved learning event, oldest first."""
        ...

    def save_event(self, event: LearningEvent) -> None:
        """Create the event, or replace it when its id exists (keeps its place in the order)."""
        ...

    def clear_events(self) -> None:
        """Delete every learning event (demo reset). Users and voices are kept."""
        ...

    def load_voices(self) -> list[VoiceProfile]:
        """Every learned voice."""
        ...

    def save_voice(self, voice: VoiceProfile) -> None:
        """Create or replace the voice with this name (case does not matter)."""
        ...

    def delete_voice(self, name: str) -> None:
        """Forget one voice, vector included. No error when it is not there."""
        ...

    def load_sessions(self) -> list[SessionRecord]:
        """Every session record, oldest first. A demo reset never deletes them."""
        ...

    def save_session(self, record: SessionRecord) -> None:
        """Add one session record (written once, never changed)."""
        ...

    def unsaved_writes(self) -> int:
        """Writes that failed and still wait for another try (0 when everything is saved)."""
        ...


class NullStorage:
    """No database: everything stays in memory, as before. Used when `DATABASE_URL` is not set."""

    def load_users(self) -> list[User]:
        """Nothing stored."""
        return []

    def seed_users(self, users: list[User]) -> None:
        """Nothing to do."""

    def save_user(self, user: User) -> None:
        """Nothing to do."""

    def load_events(self) -> list[LearningEvent]:
        """Nothing stored."""
        return []

    def save_event(self, event: LearningEvent) -> None:
        """Nothing to do."""

    def clear_events(self) -> None:
        """Nothing to do."""

    def load_voices(self) -> list[VoiceProfile]:
        """Nothing stored."""
        return []

    def save_voice(self, voice: VoiceProfile) -> None:
        """Nothing to do."""

    def delete_voice(self, name: str) -> None:
        """Nothing to do."""

    def load_sessions(self) -> list[SessionRecord]:
        """Nothing stored."""
        return []

    def save_session(self, record: SessionRecord) -> None:
        """Nothing to do."""

    def unsaved_writes(self) -> int:
        """Nothing is ever waiting."""
        return 0
