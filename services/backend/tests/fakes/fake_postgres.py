"""A `PostgresStorage` with no database whose reads can fail, for the startup fallback."""

from mochi_backend.storage.postgres import PostgresStorage
from mochi_contracts import Company, LearningEvent, Member, User, VoiceProfile


class ReadFailsPostgres(PostgresStorage):
    """Tables "exist" and seeding works, but reading the words fails like a dropped connection."""

    def prepare(self) -> None:
        """Pretend the tables exist."""

    def seed_users(self, users: list[User]) -> None:
        """Pretend the users were added."""

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Pretend the company was added."""

    def load_users(self) -> list[User]:
        """No users."""
        return []

    def load_voices(self) -> list[VoiceProfile]:
        """No voices."""
        return []

    def load_events(self) -> list[LearningEvent]:
        """The connection drops here."""
        raise ConnectionError("the database went away while loading")
