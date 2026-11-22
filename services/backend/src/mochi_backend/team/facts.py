"""Everything known about one company, as the team view's functions take it."""

from dataclasses import dataclass, field
from datetime import datetime

from mochi_backend.platform.clock import parse_iso_z
from mochi_contracts import (
    Company,
    ConversationReport,
    LearningEvent,
    Member,
    SessionRecord,
    User,
    Utterance,
    WordMoment,
)


@dataclass(frozen=True)
class TeamFacts:
    """Everything known about one company. `cards`: each member's saved words (all time)."""

    company: Company
    members: list[Member]
    users: dict[str, User]
    records: list[SessionRecord] = field(default_factory=list)
    moments: list[WordMoment] = field(default_factory=list)
    cards: dict[str, list[LearningEvent]] = field(default_factory=dict)
    reports: list[ConversationReport] = field(default_factory=list)  # what was wrong (D-54)
    said: list[Utterance] = field(default_factory=list)  # for what was explained in them (D-53)

    def since(self, start: datetime) -> "TeamFacts":
        """The same company with only the sessions, moments, reports and sentences from
        `start` on."""
        return TeamFacts(
            self.company,
            self.members,
            self.users,
            [r for r in self.records if parse_iso_z(r.started_at) >= start],
            [m for m in self.moments if parse_iso_z(m.at) >= start],
            self.cards,
            [r for r in self.reports if parse_iso_z(r.ended_at) >= start],
            [u for u in self.said if parse_iso_z(u.at) >= start],
        )
