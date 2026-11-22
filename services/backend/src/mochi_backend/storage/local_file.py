"""A `Storage` in one JSON file, for local work in fake mode (no database needed).

The file holds voiceprints, so it is created readable by its owner only. It is replaced
atomically, so a crash never leaves half a file. Not for production: a container's disk is wiped
on every deploy (see D-33).
"""

import json
import os
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from mochi_backend.platform.json_logging import EventLogger
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


class LocalFileStorage:
    """Implements `Storage`. Example: `LocalFileStorage(Path("m.json"), logger).load_events()`."""

    def __init__(self, path: Path, logger: EventLogger) -> None:
        self._path = path
        self._logger = logger
        self._users: dict[str, User] = {}
        self._events: dict[str, LearningEvent] = {}
        self._voices: dict[str, VoiceProfile] = {}
        self._companies: dict[str, Company] = {}
        self._members: dict[tuple[str, str], Member] = {}
        self._records: dict[str, SessionRecord] = {}
        self._moments: dict[str, WordMoment] = {}
        self._utterances: dict[str, Utterance] = {}
        self._reports: dict[str, ConversationReport] = {}
        self._read()

    def _read(self) -> None:
        """Load the file if there is one. Raises `ValueError`/`OSError` when it is unreadable."""
        if not self._path.exists():
            return
        saved = json.loads(self._path.read_text())
        self._users = {u.user_id: u for u in self._rows("users", saved, User)}
        self._events = {e.learning_event_id: e for e in self._rows("events", saved, LearningEvent)}
        self._voices = {voice_key(v.name): v for v in self._rows("voices", saved, VoiceProfile)}
        self._read_team(saved)

    def _read_team(self, saved: dict[str, list[object]]) -> None:
        self._companies = {c.company_id: c for c in self._rows("companies", saved, Company)}
        members = self._rows("members", saved, Member)
        self._members = {(m.company_id, m.user_id): m for m in members}
        self._records = {r.record_id: r for r in self._rows("records", saved, SessionRecord)}
        self._moments = {m.moment_id: m for m in self._rows("moments", saved, WordMoment)}
        said = self._rows("utterances", saved, Utterance)
        self._utterances = {u.utterance_id: u for u in said}
        reports = self._rows("reports", saved, ConversationReport)
        self._reports = {r.report_id: r for r in reports}

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
        tables: dict[str, Iterable[BaseModel]] = {
            "users": self._users.values(),
            "events": self._events.values(),
            "voices": self._voices.values(),
            "companies": self._companies.values(),
            "members": self._members.values(),
            "records": self._records.values(),
            "moments": self._moments.values(),
            "utterances": self._utterances.values(),
            "reports": self._reports.values(),
        }
        text = json.dumps(
            {name: [row.model_dump(mode="json") for row in rows] for name, rows in tables.items()}
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

    def save_user(self, user: User) -> None:
        """Create or replace by id."""
        self._users[user.user_id] = user
        self._write()

    def load_companies(self) -> list[Company]:
        """Every stored company."""
        return list(self._companies.values())

    def load_members(self) -> list[Member]:
        """Every stored membership."""
        return list(self._members.values())

    def seed_company(self, company: Company, members: list[Member]) -> None:
        """Add the company and the memberships that are missing."""
        self._companies.setdefault(company.company_id, company)
        for member in members:
            self._members.setdefault((member.company_id, member.user_id), member)
        self._write()

    def save_member(self, member: Member) -> None:
        """Create or replace one membership."""
        self._members[(member.company_id, member.user_id)] = member
        self._write()

    def load_records(self) -> list[SessionRecord]:
        """Records in the order first saved."""
        return list(self._records.values())

    def save_record(self, record: SessionRecord) -> None:
        """Create or replace by id (a replaced record keeps its place)."""
        self._records[record.record_id] = record
        self._write()

    def load_moments(self) -> list[WordMoment]:
        """Moments in the order saved."""
        return list(self._moments.values())

    def save_moment(self, moment: WordMoment) -> None:
        """Keep one moment."""
        self._moments.setdefault(moment.moment_id, moment)
        self._write()

    def load_utterances(self) -> list[Utterance]:
        """Sentences in the order first saved."""
        return list(self._utterances.values())

    def save_utterance(self, utterance: Utterance) -> None:
        """Create or replace by id (a replaced sentence keeps its place)."""
        self._utterances[utterance.utterance_id] = utterance
        self._write()

    def load_reports(self) -> list[ConversationReport]:
        """Reports in the order saved."""
        return list(self._reports.values())

    def save_report(self, report: ConversationReport) -> None:
        """Keep one report."""
        self._reports.setdefault(report.report_id, report)
        self._write()

    def clear_history(self) -> None:
        """Delete every record, moment, sentence and report."""
        self._records.clear()
        self._moments.clear()
        self._utterances.clear()
        self._reports.clear()
        self._write()

    def unsaved_writes(self) -> int:
        """Writes are direct here, so nothing is ever waiting."""
        return 0
