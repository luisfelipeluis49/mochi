"""The company side of Papear: members, the team view and each person's own moments (D-45).

`viewer` is the `user_id` of the person looking, as in `/ws?user=`: there is no sign-in yet.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query

from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_backend.gateway.team_service import USER_ID_PATTERN
from mochi_backend.team.team_view import DEFAULT_PERIOD_DAYS, MAX_PERIOD_DAYS
from mochi_contracts import (
    ConversationReport,
    SessionRecord,
    TeamInsights,
    TeamMember,
    Utterance,
    WordMoment,
)

router = APIRouter()
ID_PATTERN = USER_ID_PATTERN
CompanyId = Annotated[str, Path(pattern=ID_PATTERN)]
UserId = Annotated[str, Path(pattern=ID_PATTERN)]
Viewer = Annotated[str | None, Query(max_length=40)]
PeriodDays = Annotated[int, Query(ge=1, le=MAX_PERIOD_DAYS)]


@router.get("/api/companies/{company_id}/members")
async def company_members(
    company_id: CompanyId, container: ContainerDep, viewer: Viewer = None
) -> list[TeamMember]:
    """Who belongs to the company. Any member may ask.

    Example: `GET /api/companies/demo/members?viewer=ben`.
    """
    return container.team_service.members(company_id, viewer)


@router.post("/api/companies/{company_id}/members")
async def add_company_member(
    company_id: CompanyId, body: TeamMember, container: ContainerDep, viewer: Viewer = None
) -> TeamMember:
    """An administrator adds a person, or changes their role, team or languages.

    Example: `POST /api/companies/demo/members?viewer=ana` with `{"user": {"user_id": "caio",
    "display_name": "Caio", "comfortable_languages": ["pt-BR"], "target_language": "en"},
    "role": "member", "team": "Sales"}`. The person can then register their voice under that
    display name and open `/ws?user=caio`.
    """
    return container.team_service.add_member(company_id, viewer, body)


@router.get("/api/companies/{company_id}/insights")
async def company_insights(
    company_id: CompanyId,
    container: ContainerDep,
    viewer: Viewer = None,
    days: PeriodDays = DEFAULT_PERIOD_DAYS,
) -> TeamInsights:
    """The team view: every member's learning data, added up. Administrators only.

    Example: `GET /api/companies/demo/insights?viewer=ana&days=30`.
    """
    return await container.team_service.insights_in_thread(company_id, viewer, days)


@router.get("/api/companies/{company_id}/sessions")
async def company_sessions(
    company_id: CompanyId, container: ContainerDep, viewer: Viewer = None
) -> list[SessionRecord]:
    """Every meeting and review of the company, newest first. Administrators only.

    Example: `GET /api/companies/demo/sessions?viewer=ana`. No sentence is in it.
    """
    return container.team_service.sessions(company_id, viewer)


@router.get("/api/users/{user_id}/moments")
async def user_moments(
    user_id: UserId, container: ContainerDep, viewer: Viewer = None
) -> list[WordMoment]:
    """Each time this person needed a word, newest first, with their own sentence.

    Example: `GET /api/users/ana/moments?viewer=ana`. Only the person themselves may ask.
    """
    return container.team_service.moments_of(user_id, viewer)


@router.get("/api/users/{user_id}/utterances")
async def user_utterances(
    user_id: UserId, container: ContainerDep, viewer: Viewer = None
) -> list[Utterance]:
    """Everything this person said in their sessions, newest first.

    Example: `GET /api/users/ana/utterances?viewer=ana`. Only the person themselves may ask;
    what the others in a meeting said is never in it.
    """
    return container.team_service.sentences_of(user_id, viewer)


@router.get("/api/users/{user_id}/reports")
async def user_reports(
    user_id: UserId, container: ContainerDep, viewer: Viewer = None
) -> list[ConversationReport]:
    """What was wrong or inaccurate in what this person said, one report per session, newest
    first: their sentences put right, the kinds of mistake, the words they needed.

    Example: `GET /api/users/ana/reports?viewer=ana`. Only the person themselves may ask;
    nothing of it is shown during a meeting or to an administrator.
    """
    return container.team_service.reports_of(user_id, viewer)
