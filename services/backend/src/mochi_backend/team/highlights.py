"""The few things in a team view worth an administrator's attention. Pure functions.

A highlight is a kind plus numbers; the screen writes the sentence in the reader's language.
"""

from mochi_backend.team.gaps import share_of
from mochi_backend.team.progress import AT_LEAST_ASSISTED, AT_LEAST_REINFORCED, reached
from mochi_contracts import Highlight, LearningEvent, LearningFunnel, SharedGap

SHARED_BY = 2  # "shared" starts at two people
REPEATED_TIMES = 3  # needed this often, and still nobody used it afterwards


def _used_expressions(cards: dict[str, list[LearningEvent]]) -> set[str]:
    """Expressions at least one person went on to use (with help or better)."""
    every = [card for mine in cards.values() for card in mine]
    return {card.expression.lower() for card in every if reached(card, AT_LEAST_ASSISTED)}


def _shared(gaps: list[SharedGap]) -> list[Highlight]:
    top = next((gap for gap in gaps if gap.people >= SHARED_BY), None)
    if top is None:
        return []
    return [
        Highlight(kind="shared_gap", expression=top.expression, people=top.people, times=top.times)
    ]


def _repeated(gaps: list[SharedGap], cards: dict[str, list[LearningEvent]]) -> list[Highlight]:
    used = _used_expressions(cards)
    stuck = [g for g in gaps if g.times >= REPEATED_TIMES and g.expression.lower() not in used]
    if not stuck:
        return []
    worst = max(stuck, key=lambda gap: gap.times)
    return [
        Highlight(
            kind="repeated_gap", expression=worst.expression, people=worst.people, times=worst.times
        )
    ]


def _false_friend(friends: list[SharedGap]) -> list[Highlight]:
    if not friends:
        return []
    top = max(friends, key=lambda gap: (gap.times, gap.people))
    return [
        Highlight(
            kind="false_friend", expression=top.expression, people=top.people, times=top.times
        )
    ]


def _sticking(funnel: LearningFunnel) -> list[Highlight]:
    if funnel.discovered == 0:
        return []
    share = share_of(funnel.assisted, funnel.discovered)
    return [Highlight(kind="words_sticking", times=funnel.assisted, share=share)]


def _backlog(cards: dict[str, list[LearningEvent]]) -> list[Highlight]:
    waiting = {
        user: sum(1 for card in mine if not reached(card, AT_LEAST_REINFORCED))
        for user, mine in cards.items()
    }
    people = sum(1 for count in waiting.values() if count)
    if people == 0:
        return []
    return [Highlight(kind="review_backlog", people=people, times=sum(waiting.values()))]


def highlights_for(
    gaps: list[SharedGap],
    friends: list[SharedGap],
    funnel: LearningFunnel,
    cards: dict[str, list[LearningEvent]],
) -> list[Highlight]:
    """At most one highlight of each kind, the most actionable first.

    Example: three people needed "postpone" -> `Highlight(kind="shared_gap", expression=
    "postpone", people=3, times=5)`.
    """
    return [
        *_shared(gaps),
        *_repeated(gaps, cards),
        *_false_friend(friends),
        *_sticking(funnel),
        *_backlog(cards),
    ]
