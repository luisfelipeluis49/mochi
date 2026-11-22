"""How far saved words got, for the whole team and for each member. Pure functions."""

from mochi_backend.team.facts import TeamFacts
from mochi_contracts import (
    LearningEvent,
    LearningFunnel,
    LearningState,
    Member,
    MemberProgress,
    SessionMode,
    SessionRecord,
)

# Every state a card may have passed through when it is at least "used with help", and so on.
AT_LEAST_ASSISTED = (
    LearningState.ASSISTED,
    LearningState.REINFORCED,
    LearningState.USED_INDEPENDENTLY,
)
AT_LEAST_REINFORCED = (LearningState.REINFORCED, LearningState.USED_INDEPENDENTLY)


def reached(card: LearningEvent, states: tuple[LearningState, ...]) -> bool:
    """True when the card was ever in one of `states` (its history, not just where it is now).

    Example: a card that went DISCOVERED -> REINFORCED reached AT_LEAST_ASSISTED.
    """
    return any(change.learning_state in states for change in card.state_history)


def funnel_of(cards: dict[str, list[LearningEvent]]) -> LearningFunnel:
    """How many of everyone's saved words got at least this far.

    Example: three cards, one of them recalled in a review -> discovered 3, reinforced 1.
    """
    every = [card for mine in cards.values() for card in mine]
    return LearningFunnel(
        discovered=len(every),
        assisted=sum(reached(card, AT_LEAST_ASSISTED) for card in every),
        reinforced=sum(reached(card, AT_LEAST_REINFORCED) for card in every),
        used_independently=sum(reached(c, (LearningState.USED_INDEPENDENTLY,)) for c in every),
    )


def _last_active(facts: TeamFacts, user_id: str) -> str | None:
    """The latest moment, or end of a session this person spoke or reviewed in."""
    stamps = [m.at for m in facts.moments if m.user_id == user_id]
    for record in facts.records:
        spoke = any(share.user_id == user_id for share in record.speaking)
        reviewed = record.mode is SessionMode.REVIEW and user_id in record.participants
        if spoke or reviewed:
            stamps.append(record.ended_at or record.started_at)
    return max(stamps) if stamps else None


def _row(facts: TeamFacts, member: Member) -> MemberProgress:
    user, uid = facts.users[member.user_id], member.user_id
    spoken = [s for r in facts.records for s in r.speaking if s.user_id == uid]
    reviews = [r for r in facts.records if r.mode is SessionMode.REVIEW and uid in r.participants]
    cards = facts.cards.get(uid, [])
    return MemberProgress(
        user_id=uid,
        display_name=user.display_name,
        role=member.role,
        team=member.team,
        target_language=user.target_language,
        meetings=_meetings_taken_part_in(facts, uid),
        reviews=len(reviews),
        speaking_turns=sum(share.turns for share in spoken),
        moments=sum(1 for m in facts.moments if m.user_id == uid),
        words=len(cards),
        assisted=sum(reached(card, AT_LEAST_ASSISTED) for card in cards),
        reinforced=sum(reached(card, AT_LEAST_REINFORCED) for card in cards),
        last_active_at=_last_active(facts, uid),
    )


def _took_part(record: SessionRecord, user_id: str, stuck_in: set[str | None]) -> bool:
    spoke = any(share.user_id == user_id for share in record.speaking)
    return record.mode is SessionMode.MEETING and (spoke or record.record_id in stuck_in)


def _meetings_taken_part_in(facts: TeamFacts, user_id: str) -> int:
    """Meetings in which this person's voice was recognised, or a word was theirs.

    A phone's microphone recognises no voice, so there the moments are the only trace.
    """
    stuck_in = {moment.record_id for moment in facts.moments if moment.user_id == user_id}
    return sum(_took_part(record, user_id, stuck_in) for record in facts.records)


def member_rows(facts: TeamFacts) -> list[MemberProgress]:
    """One row per member the roster knows, by name: counts only.

    Example: `member_rows(facts)[0].display_name` is "Ana".
    """
    known = [member for member in facts.members if member.user_id in facts.users]
    rows = [_row(facts, member) for member in known]
    return sorted(rows, key=lambda row: row.display_name.lower())
