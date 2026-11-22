"""The company routes' logic: who may see what, adding members, and the team view.

There is no sign-in in the MVP (AGENTS 6.4), so `viewer` is the `user_id` the caller says they
are, exactly as `/ws?user=ana` is. The role rules below are the real ones; only the proof of
identity is missing, and it slots in here when sign-in exists.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from mochi_backend.gateway.errors import ForbiddenError, InvalidRequestError, NotFoundError
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.roster import Roster
from mochi_backend.platform.clock import Clock
from mochi_backend.team.facts import TeamFacts
from mochi_backend.team.ledger import TeamLedger
from mochi_backend.team.team_view import team_insights
from mochi_contracts import (
    Company,
    ConversationReport,
    Member,
    MemberRole,
    SessionRecord,
    TeamInsights,
    TeamMember,
    Utterance,
    WordMoment,
)


@dataclass(frozen=True)
class TeamSources:
    """Where the team view's facts come from: the history, the people and their saved words."""

    ledger: TeamLedger
    roster: Roster
    words: IntelligencePort
    # People outside the company who still have a page of their own: the web app's users (D-56).
    also_known: Callable[[str], bool] = lambda user_id: False  # noqa: E731 - a default


USER_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,39}$"  # what `/ws?user=` and `/api/users/{id}` take


def check_joining(joining: TeamMember) -> None:
    """Raise `InvalidRequestError` unless the person has a usable id and a name.

    Example: `user_id` "Caio Lima" is refused: lower-case letters, digits, - and _ only.
    """
    user = joining.user
    if re.fullmatch(USER_ID_PATTERN, user.user_id) is None:
        raise InvalidRequestError(
            f"bad user_id {user.user_id[:40]!r}; expected 1-40 of a-z, 0-9, - and _, "
            f"starting with a letter or digit, e.g. 'caio'"
        )
    if not user.display_name.strip():
        raise InvalidRequestError(
            f"empty display_name for {user.user_id!r}; expected the name the person says, "
            f"e.g. 'Caio' (their voice is registered under it)"
        )


class TeamService:
    """Example: `service.insights("demo", viewer="ana", period_days=30)`."""

    def __init__(self, sources: TeamSources, clock: Clock, min_people: int = 1) -> None:
        self._ledger = sources.ledger
        self._roster = sources.roster
        self._words = sources.words
        self._also_known = sources.also_known
        self._clock = clock
        self._min_people = min_people

    def _company(self, company_id: str) -> Company:
        company = self._ledger.company(company_id)
        if company is None:
            raise NotFoundError(f"unknown company {company_id!r}")
        return company

    def _allow(self, company_id: str, viewer: str | None, admin_only: bool) -> Company:
        """The company, when `viewer` belongs to it (and is an administrator if that is needed)."""
        company = self._company(company_id)
        role = self._ledger.role_of(company_id, viewer)
        if role is None:
            raise ForbiddenError(f"viewer {viewer!r} is not a member of company {company_id!r}")
        if admin_only and role is not MemberRole.ADMIN:
            raise ForbiddenError(f"viewer {viewer!r} is not an administrator of {company_id!r}")
        return company

    def members(self, company_id: str, viewer: str | None) -> list[TeamMember]:
        """Who belongs to the company; any member may ask."""
        self._allow(company_id, viewer, admin_only=False)
        return [
            TeamMember(user=user, role=member.role, team=member.team)
            for member in self._ledger.members_of(company_id)
            if (user := self._roster.user(member.user_id)) is not None
        ]

    def add_member(self, company_id: str, viewer: str | None, joining: TeamMember) -> TeamMember:
        """An administrator adds a person (or changes their role, team or languages)."""
        self._allow(company_id, viewer, admin_only=True)
        check_joining(joining)
        self._roster.add(joining.user)
        member = Member(
            company_id=company_id,
            user_id=joining.user.user_id,
            role=joining.role,
            team=joining.team,
        )
        self._ledger.keep_member(joining.user, member)
        return joining

    def _facts(self, company: Company) -> TeamFacts:
        members = self._ledger.members_of(company.company_id)
        return TeamFacts(
            company=company,
            members=members,
            users={user.user_id: user for user in self._roster.users()},
            records=self._ledger.records_of(company.company_id),
            moments=self._ledger.moments_of(company.company_id),
            cards={member.user_id: self._words.words_for(member.user_id) for member in members},
            reports=self._ledger.reports_of(company.company_id),
            said=self._ledger.utterances_of(company.company_id),
        )

    def insights(self, company_id: str, viewer: str | None, period_days: int) -> TeamInsights:
        """The team view for the last `period_days`; administrators only."""
        company = self._allow(company_id, viewer, admin_only=True)
        return team_insights(self._facts(company), self._clock.now(), period_days, self._min_people)

    def sessions(self, company_id: str, viewer: str | None) -> list[SessionRecord]:
        """Every session of the company, newest first; administrators only. No sentences."""
        self._allow(company_id, viewer, admin_only=True)
        return list(reversed(self._ledger.records_of(company_id)))

    def _is_person(self, user_id: str) -> bool:
        """Someone with a page of their own: a company's person, or a user the web app made."""
        return self._roster.knows(user_id) or self._also_known(user_id)

    def moments_of(self, user_id: str, viewer: str | None) -> list[WordMoment]:
        """A person's own moments, newest first, with the sentence each word was needed in.

        Only that person may ask: a manager sees the team's numbers, never someone's sentences.
        """
        if viewer != user_id or not self._is_person(user_id):
            raise ForbiddenError(f"viewer {viewer!r} may only read their own moments")
        mine = [
            moment
            for company_id in self._ledger.companies_of(user_id)
            for moment in self._ledger.moments_of(company_id)
            if moment.user_id == user_id
        ]
        return sorted(mine, key=lambda moment: moment.at, reverse=True)

    def sentences_of(self, user_id: str, viewer: str | None) -> list[Utterance]:
        """What a person said in their sessions, newest first. Only that person may ask.

        Example: `service.sentences_of("ana", "ana")[0].text`.
        """
        if viewer != user_id or not self._is_person(user_id):
            raise ForbiddenError(f"viewer {viewer!r} may only read their own sentences")
        return list(reversed(self._ledger.utterances_by(user_id)))

    def reports_of(self, user_id: str, viewer: str | None) -> list[ConversationReport]:
        """What Mochi noticed in a person's speech, session by session, newest first (D-54).

        Only that person may ask. Example: `service.reports_of("ana", "ana")[0].mistakes`.
        """
        if viewer != user_id or not self._is_person(user_id):
            raise ForbiddenError(f"viewer {viewer!r} may only read their own reports")
        return list(reversed(self._ledger.reports_by(user_id)))
