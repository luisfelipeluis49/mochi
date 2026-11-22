"""The company half of `PostgresStorage`: companies, members, session records, word moments."""

from mochi_backend.storage import schema
from mochi_backend.storage.postgres_base import PostgresBase, Row
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


class PostgresTeamTables(PostgresBase):
    """`PostgresStorage` builds on this. Example: `PostgresStorage(url, logger).load_moments()`."""

    def save_user(self, user: User) -> None:
        """Insert or replace one user by id."""
        languages = [language.value for language in user.comfortable_languages]
        params = (user.user_id, user.display_name, languages, user.target_language.value)
        self._run(schema.UPSERT_USER, params)

    def load_companies(self) -> list[Company]:
        """Every company, oldest first."""
        return [
            Company(company_id=str(row[0]), name=str(row[1]))
            for row in self._rows(schema.SELECT_COMPANIES)
        ]

    def load_members(self) -> list[Member]:
        """Every membership, oldest first. A row that no longer fits the contract is skipped."""
        return self._parsed("company_members", self._rows(schema.SELECT_MEMBERS), _member)

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Insert the company and the memberships that do not exist yet."""
        with self._connect() as connection:
            connection.execute(schema.INSERT_COMPANY, (company.company_id, company.name))
            for member in members:
                connection.execute(schema.INSERT_MEMBER, _member_params(member))

    def save_member(self, member: Member) -> None:
        """Insert or replace one membership."""
        self._run(schema.UPSERT_MEMBER, _member_params(member))

    def load_records(self) -> list[SessionRecord]:
        """Every session record in the order it was first saved."""
        return self._parsed("session_records", self._rows(schema.SELECT_RECORDS), _record)

    def save_record(self, record: SessionRecord) -> None:
        """Insert the record, or update how it ended."""
        params = (
            record.record_id,
            record.company_id,
            record.session_id,
            record.mode.value,
            record.started_at,
            record.ended_at,
            record.model_dump_json(),
        )
        self._run(schema.UPSERT_RECORD, params)

    def load_moments(self) -> list[WordMoment]:
        """Every word moment in the order it was saved."""
        return self._parsed("word_moments", self._rows(schema.SELECT_MOMENTS), _moment)

    def save_moment(self, moment: WordMoment) -> None:
        """Insert one moment (a second save of the same id changes nothing)."""
        params = (
            moment.moment_id,
            moment.company_id,
            moment.record_id,
            moment.user_id,
            moment.expression,
            moment.target_language.value,
            moment.reason.value,
            moment.at,
            moment.model_dump_json(),
        )
        self._run(schema.INSERT_MOMENT, params)

    def load_utterances(self) -> list[Utterance]:
        """Every recorded sentence in the order it was first saved."""
        return self._parsed("utterances", self._rows(schema.SELECT_UTTERANCES), _utterance)

    def save_utterance(self, utterance: Utterance) -> None:
        """Insert the sentence, or update who said it."""
        params = (
            utterance.utterance_id,
            utterance.company_id,
            utterance.record_id,
            utterance.user_id,
            utterance.at,
            utterance.model_dump_json(),
        )
        self._run(schema.UPSERT_UTTERANCE, params)

    def load_reports(self) -> list[ConversationReport]:
        """Every conversation report in the order it was saved."""
        return self._parsed("conversation_reports", self._rows(schema.SELECT_REPORTS), _report)

    def save_report(self, report: ConversationReport) -> None:
        """Insert one report (a second save of the same id changes nothing)."""
        params = (
            report.report_id,
            report.company_id,
            report.record_id,
            report.user_id,
            report.ended_at,
            report.model_dump_json(),
        )
        self._run(schema.INSERT_REPORT, params)

    def clear_history(self) -> None:
        """Delete every report, sentence, word moment and session record."""
        with self._connect() as connection:
            connection.execute(schema.DELETE_REPORTS)
            connection.execute(schema.DELETE_UTTERANCES)
            connection.execute(schema.DELETE_MOMENTS)
            connection.execute(schema.DELETE_RECORDS)


def _member_params(member: Member) -> tuple[object, ...]:
    return (member.company_id, member.user_id, member.role.value, member.team)


def _member(row: Row) -> Member:
    return Member(
        company_id=str(row[0]),
        user_id=str(row[1]),
        role=MemberRole(str(row[2])),
        team=None if row[3] is None else str(row[3]),
    )


def _record(row: Row) -> SessionRecord:
    return SessionRecord.model_validate_json(str(row[1]))


def _moment(row: Row) -> WordMoment:
    return WordMoment.model_validate_json(str(row[1]))


def _report(row: Row) -> ConversationReport:
    return ConversationReport.model_validate_json(str(row[1]))


def _utterance(row: Row) -> Utterance:
    return Utterance.model_validate_json(str(row[1]))
