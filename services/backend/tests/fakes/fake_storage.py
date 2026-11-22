"""A `Storage` that keeps everything in lists and can be told to fail. No database."""

from mochi_backend.storage.port import voice_key
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


class FakeStorage:
    """Implements `Storage`. Set `broken` to make every call raise, like a database that is down."""

    def __init__(self, users: list[User] | None = None) -> None:
        self.users: list[User] = list(users or [])
        self.events: dict[str, LearningEvent] = {}
        self.voices: dict[str, VoiceProfile] = {}
        self.companies: dict[str, Company] = {}
        self.members: dict[tuple[str, str], Member] = {}
        self.records: dict[str, SessionRecord] = {}
        self.moments: dict[str, WordMoment] = {}
        self.utterances: dict[str, Utterance] = {}
        self.reports: dict[str, ConversationReport] = {}
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

    def save_user(self, user: User) -> None:
        """Create or replace by id."""
        self._enter("save_user")
        self.users = [u for u in self.users if u.user_id != user.user_id] + [user]

    def load_companies(self) -> list[Company]:
        """The stored companies."""
        self._enter("load_companies")
        return list(self.companies.values())

    def load_members(self) -> list[Member]:
        """The stored memberships."""
        self._enter("load_members")
        return list(self.members.values())

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Add the company and the memberships that are missing."""
        self._enter("seed_company")
        self.companies.setdefault(company.company_id, company)
        for member in members:
            self.members.setdefault((member.company_id, member.user_id), member)

    def save_member(self, member: Member) -> None:
        """Create or replace one membership."""
        self._enter("save_member")
        self.members[(member.company_id, member.user_id)] = member

    def load_records(self) -> list[SessionRecord]:
        """Records in the order first saved."""
        self._enter("load_records")
        return list(self.records.values())

    def save_record(self, record: SessionRecord) -> None:
        """Create or replace by id."""
        self._enter("save_record")
        self.records[record.record_id] = record

    def load_moments(self) -> list[WordMoment]:
        """Moments in the order saved."""
        self._enter("load_moments")
        return list(self.moments.values())

    def save_moment(self, moment: WordMoment) -> None:
        """Keep one moment."""
        self._enter("save_moment")
        self.moments.setdefault(moment.moment_id, moment)

    def load_utterances(self) -> list[Utterance]:
        """Sentences in the order first saved."""
        self._enter("load_utterances")
        return list(self.utterances.values())

    def save_utterance(self, utterance: Utterance) -> None:
        """Create or replace by id."""
        self._enter("save_utterance")
        self.utterances[utterance.utterance_id] = utterance

    def load_reports(self) -> list[ConversationReport]:
        """Reports in the order saved."""
        self._enter("load_reports")
        return list(self.reports.values())

    def save_report(self, report: ConversationReport) -> None:
        """Keep one report."""
        self._enter("save_report")
        self.reports.setdefault(report.report_id, report)

    def clear_history(self) -> None:
        """Delete every record, moment, sentence and report."""
        self._enter("clear_history")
        self.reports.clear()
        self.records.clear()
        self.moments.clear()
        self.utterances.clear()

    def unsaved_writes(self) -> int:
        """Nothing waits in a fake."""
        return 0
