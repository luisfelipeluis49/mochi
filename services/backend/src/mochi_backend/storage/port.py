"""What the backend needs from a database. Postgres implements it; tests use a fake."""

from typing import Protocol

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


def voice_key(name: str) -> str:
    """The case-insensitive key of a voice name. Example: `voice_key(" Ana ")` is `"ana"`."""
    return name.strip().casefold()


class Storage(Protocol):
    """Durable copies of users, learning events, voices and the company's learning history.

    Reads happen once, at startup. The company part (DECISIONS D-45): who belongs to which
    company, one record per session, and one moment per time someone needed a word.
    """

    def load_users(self) -> list[User]:
        """Every known user (empty when nothing is stored)."""
        ...

    def seed_users(self, users: list[User]) -> None:
        """Add users that are missing; never overwrites one that exists."""
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

    def save_user(self, user: User) -> None:
        """Create the user, or replace the one with this id (a member added or edited)."""
        ...

    def load_companies(self) -> list[Company]:
        """Every company."""
        ...

    def load_members(self) -> list[Member]:
        """Every membership, of every company."""
        ...

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Add the company and the memberships that are missing; never overwrites one."""
        ...

    def save_member(self, member: Member) -> None:
        """Create or replace one person's membership of one company."""
        ...

    def load_records(self) -> list[SessionRecord]:
        """Every session record, oldest first."""
        ...

    def save_record(self, record: SessionRecord) -> None:
        """Create the record, or replace it when its id exists (a session that ended)."""
        ...

    def load_moments(self) -> list[WordMoment]:
        """Every word moment, oldest first."""
        ...

    def save_moment(self, moment: WordMoment) -> None:
        """Keep one moment (they are never changed)."""
        ...

    def load_utterances(self) -> list[Utterance]:
        """Every recorded sentence, oldest first."""
        ...

    def save_utterance(self, utterance: Utterance) -> None:
        """Keep one sentence, or replace it when its id exists (its speaker became known)."""
        ...

    def load_reports(self) -> list[ConversationReport]:
        """Every conversation report, oldest first (DECISIONS D-54)."""
        ...

    def save_report(self, report: ConversationReport) -> None:
        """Keep one person's report of one session (they are never changed)."""
        ...

    def clear_history(self) -> None:
        """Delete every session record, word moment, sentence and report (demo reset). People
        are kept."""
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

    def save_user(self, user: User) -> None:
        """Nothing to do."""

    def load_companies(self) -> list[Company]:
        """Nothing stored."""
        return []

    def load_members(self) -> list[Member]:
        """Nothing stored."""
        return []

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Nothing to do."""

    def save_member(self, member: Member) -> None:
        """Nothing to do."""

    def load_records(self) -> list[SessionRecord]:
        """Nothing stored."""
        return []

    def save_record(self, record: SessionRecord) -> None:
        """Nothing to do."""

    def load_moments(self) -> list[WordMoment]:
        """Nothing stored."""
        return []

    def save_moment(self, moment: WordMoment) -> None:
        """Nothing to do."""

    def load_utterances(self) -> list[Utterance]:
        """Nothing stored."""
        return []

    def save_utterance(self, utterance: Utterance) -> None:
        """Nothing to do."""

    def load_reports(self) -> list[ConversationReport]:
        """Nothing stored."""
        return []

    def save_report(self, report: ConversationReport) -> None:
        """Nothing to do."""

    def clear_history(self) -> None:
        """Nothing to do."""

    def unsaved_writes(self) -> int:
        """Nothing is ever waiting."""
        return 0
