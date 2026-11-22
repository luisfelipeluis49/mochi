"""The team view: every member's learning data, added up for an administrator (DECISIONS D-45).

Pure functions: facts in, `TeamInsights` out. Expressions carry how many people needed them,
never who; a member's row carries counts only, no words and no sentences.
"""

from datetime import datetime, timedelta

from mochi_backend.platform.clock import iso_z, parse_iso_z
from mochi_backend.team.facts import TeamFacts
from mochi_backend.team.gaps import gaps_in, reason_counts, split_by_kind
from mochi_backend.team.highlights import highlights_for
from mochi_backend.team.progress import funnel_of, member_rows
from mochi_backend.team.speech import explained_in, mistakes_in
from mochi_contracts import (
    SessionMode,
    SessionRecord,
    TeamInsights,
    TeamTotals,
    WeekActivity,
)

DEFAULT_PERIOD_DAYS = 30
MAX_PERIOD_DAYS = 365


def minutes_of(record: SessionRecord) -> int:
    """How long a finished session ran, in whole minutes (0 while it runs).

    Example: 16:00:00 to 16:30:20 is 30.
    """
    if record.ended_at is None:
        return 0
    length = parse_iso_z(record.ended_at) - parse_iso_z(record.started_at)
    return round(length / timedelta(minutes=1))


def active_people(facts: TeamFacts) -> set[str]:
    """Members who spoke in a session, reviewed, or needed a word.

    Example: Ana spoke in a meeting and Ben was only on the list -> {"ana"}.
    """
    spoke = {s.user_id for r in facts.records for s in r.speaking if s.user_id}
    reviewed = {u for r in facts.records if r.mode is SessionMode.REVIEW for u in r.participants}
    stuck = {m.user_id for m in facts.moments if m.user_id}
    return (spoke | reviewed | stuck) & {member.user_id for member in facts.members}


def totals_of(facts: TeamFacts) -> TeamTotals:
    """The headline numbers. Example: `totals_of(facts).meetings` is 6."""
    meetings = [r for r in facts.records if r.mode is SessionMode.MEETING]
    return TeamTotals(
        members=len(facts.members),
        active_members=len(active_people(facts)),
        meetings=len(meetings),
        reviews=len(facts.records) - len(meetings),
        meeting_minutes=sum(minutes_of(r) for r in meetings),
        moments=len(facts.moments),
        words=len({m.expression.lower() for m in facts.moments}),
    )


def monday_of(moment: datetime) -> datetime:
    """Midnight of that week's Monday. Example: Thursday 2026-11-19 -> Monday 2026-11-16."""
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


def _week(facts: TeamFacts, start: datetime) -> WeekActivity:
    end = start + timedelta(days=7)
    moments = [m for m in facts.moments if start <= parse_iso_z(m.at) < end]
    cards = [card for mine in facts.cards.values() for card in mine]
    born = [c for c in cards if start <= parse_iso_z(c.state_history[0].at) < end]
    meetings = [
        r
        for r in facts.records
        if r.mode is SessionMode.MEETING and start <= parse_iso_z(r.started_at) < end
    ]
    return WeekActivity(
        week_start=start.date().isoformat(),
        meetings=len(meetings),
        moments=len(moments),
        people=len({m.user_id for m in moments if m.user_id}),
        new_words=len(born),
    )


def weeks_of(facts: TeamFacts, since: datetime, now: datetime) -> list[WeekActivity]:
    """One row per week from `since` to `now`, quiet weeks included (a chart needs the zeros).

    Example: a 30-day period gives five rows.
    """
    weeks: list[WeekActivity] = []
    start = monday_of(since)
    while start <= now:
        weeks.append(_week(facts, start))
        start += timedelta(days=7)
    return weeks


def team_insights(
    facts: TeamFacts, now: datetime, period_days: int = DEFAULT_PERIOD_DAYS, min_people: int = 1
) -> TeamInsights:
    """The whole team view for the last `period_days` (the funnel and saved words are all time).

    Example: `team_insights(facts, clock.now()).shared_gaps[0].expression` is "postpone".
    """
    since = now - timedelta(days=period_days)
    recent = facts.since(since)
    missing, wrong = split_by_kind(recent.moments)
    funnel = funnel_of(facts.cards)
    gaps, friends = gaps_in(missing, min_people), gaps_in(wrong, min_people)
    return TeamInsights(
        company=facts.company,
        generated_at=iso_z(now),
        period_days=period_days,
        totals=totals_of(recent),
        funnel=funnel,
        signals=reason_counts(recent.moments),
        shared_gaps=gaps,
        false_friends=friends,
        mistakes=mistakes_in(recent.reports, min_people),
        explained=explained_in(recent.said),
        weekly=weeks_of(recent, since, now),
        members=member_rows(recent),
        highlights=highlights_for(gaps, friends, funnel, facts.cards),
    )
