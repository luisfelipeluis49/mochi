"""The company's learning history, in memory: who belongs where, each session, each word moment.

Loaded once at startup and written behind, like saved words (DECISIONS D-32, D-45). It holds facts
only; `team_view.py` turns them into numbers. Nothing here imports the gateway or intelligence.
"""

from mochi_backend.storage.factory import TeamStart
from mochi_backend.storage.port import Storage
from mochi_contracts import (
    Company,
    ConversationReport,
    Member,
    MemberRole,
    SessionRecord,
    User,
    Utterance,
    WordMoment,
)


class TeamLedger:
    """Example: `TeamLedger(storage, start, company, members).role_of("demo", "ana")`.

    `company` and `members` are used when storage held no company (memory only, or a first run).
    """

    def __init__(
        self, storage: Storage, start: TeamStart, company: Company, members: list[Member]
    ) -> None:
        self._storage = storage
        companies = start.companies or [company]
        self._companies = {c.company_id: c for c in companies}
        self._members = {(m.company_id, m.user_id): m for m in start.members or members}
        self._records = {r.record_id: r for r in start.records}
        self._moments = list(start.moments)
        self._utterances = {u.utterance_id: u for u in start.utterances}
        self._reports = list(start.reports)

    def company(self, company_id: str) -> Company | None:
        """The company with this id, or None."""
        return self._companies.get(company_id)

    def members_of(self, company_id: str) -> list[Member]:
        """The company's memberships, oldest first."""
        return [m for m in self._members.values() if m.company_id == company_id]

    def role_of(self, company_id: str, user_id: str | None) -> MemberRole | None:
        """What this person is in this company; None when they do not belong to it."""
        member = self._members.get((company_id, user_id or ""))
        return member.role if member else None

    def companies_of(self, user_id: str) -> list[str]:
        """Ids of the companies this person belongs to. Example: `["demo"]`."""
        return [company for company, user in self._members if user == user_id]

    def keep_member(self, user: User, member: Member) -> None:
        """Add a person to a company, or change their role, team or languages."""
        self._members[(member.company_id, member.user_id)] = member
        self._storage.save_user(user)  # before the membership: it refers to the user
        self._storage.save_member(member)

    def keep_record(self, record: SessionRecord) -> None:
        """Keep a session record: when it starts, and again when it ends."""
        self._records[record.record_id] = record
        self._storage.save_record(record)

    def keep_moment(self, moment: WordMoment) -> None:
        """Keep one time someone needed a word."""
        self._moments.append(moment)
        self._storage.save_moment(moment)

    def keep_utterance(self, utterance: Utterance) -> None:
        """Keep one sentence; again with the same id when its speaker became known."""
        self._utterances[utterance.utterance_id] = utterance
        self._storage.save_utterance(utterance)

    def utterance(self, utterance_id: str) -> Utterance | None:
        """One kept sentence, or None. Example: `ledger.utterance("seg_009")`."""
        return self._utterances.get(utterance_id)

    def utterances_of(self, company_id: str) -> list[Utterance]:
        """Every sentence kept for the company, oldest first."""
        return [u for u in self._utterances.values() if u.company_id == company_id]

    def record(self, record_id: str) -> SessionRecord | None:
        """One session record, or None once it was cleared (a demo reset)."""
        return self._records.get(record_id)

    def keep_report(self, report: ConversationReport) -> None:
        """Keep one person's report of one session (DECISIONS D-54)."""
        self._reports.append(report)
        self._storage.save_report(report)

    def reports_by(self, user_id: str) -> list[ConversationReport]:
        """One person's reports, oldest first."""
        return [r for r in self._reports if r.user_id == user_id]

    def reports_of(self, company_id: str) -> list[ConversationReport]:
        """The company's reports, oldest first (the team view counts their mistakes)."""
        return [r for r in self._reports if r.company_id == company_id]

    def utterances_in(self, record_id: str) -> list[Utterance]:
        """One session's sentences, in the order they were said."""
        return [u for u in self._utterances.values() if u.record_id == record_id]

    def utterances_by(self, user_id: str) -> list[Utterance]:
        """Everything one person said, oldest first."""
        return [u for u in self._utterances.values() if u.user_id == user_id]

    def records_of(self, company_id: str) -> list[SessionRecord]:
        """The company's session records, oldest first."""
        return [r for r in self._records.values() if r.company_id == company_id]

    def moments_of(self, company_id: str) -> list[WordMoment]:
        """The company's word moments, oldest first."""
        return [m for m in self._moments if m.company_id == company_id]

    def clear_history(self) -> None:
        """Forget every record, moment, sentence and report (demo reset). Companies and
        members stay."""
        self._reports.clear()
        self._records.clear()
        self._moments.clear()
        self._utterances.clear()
        self._storage.clear_history()
