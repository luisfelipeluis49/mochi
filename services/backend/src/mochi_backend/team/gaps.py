"""Which expressions a team needed, and how its people get stuck. Pure functions over moments."""

from collections import Counter
from collections.abc import Iterable

from mochi_contracts import Reason, ReasonCount, SharedGap, WordMoment

SHARE_DIGITS = 3


def share_of(part: int, whole: int) -> float:
    """`part / whole` rounded, 0.0 when there is nothing. Example: `share_of(1, 3)` is 0.333."""
    return round(part / whole, SHARE_DIGITS) if whole else 0.0


def reason_counts(moments: Iterable[WordMoment]) -> list[ReasonCount]:
    """How often each way of getting stuck happened, most frequent first.

    Example: two code switches and one false friend -> code_switch 0.667, look_alike 0.333.
    """
    counted = Counter(moment.reason for moment in moments)
    total = sum(counted.values())
    ordered = sorted(counted.items(), key=lambda pair: (-pair[1], pair[0].value))
    return [
        ReasonCount(reason=reason, times=times, share=share_of(times, total))
        for reason, times in ordered
    ]


def _gap(moments: list[WordMoment]) -> SharedGap:
    """One expression's moments as a gap. The newest moment names it and gives its meaning."""
    newest = max(moments, key=lambda moment: moment.at)
    meanings = [m.meaning for m in sorted(moments, key=lambda m: m.at) if m.meaning]
    return SharedGap(
        expression=newest.expression,
        meaning=meanings[-1] if meanings else None,
        target_language=newest.target_language,
        people=len({m.user_id for m in moments if m.user_id is not None}),
        times=len(moments),
        reasons=reason_counts(moments),
        last_at=newest.at,
    )


def gaps_in(moments: Iterable[WordMoment], min_people: int = 1, top: int = 10) -> list[SharedGap]:
    """The expressions needed, the ones most people share first: by whom is never said.

    `min_people`: leave out an expression fewer people needed, so a small team's list cannot
    point at one person. 1 shows everything, also what only unknown voices needed (a phone's
    microphone recognises nobody, so `people` is 0 there).
    Example: "postpone" needed by Ana twice and Ben once -> people 2, times 3.
    """
    grouped: dict[tuple[str, str], list[WordMoment]] = {}
    for moment in moments:
        key = (moment.expression.lower(), moment.target_language.value)
        grouped.setdefault(key, []).append(moment)
    gaps = [_gap(group) for group in grouped.values()]
    kept = [gap for gap in gaps if min_people <= 1 or gap.people >= min_people]
    return sorted(kept, key=lambda gap: (-gap.people, -gap.times, gap.expression.lower()))[:top]


def split_by_kind(moments: list[WordMoment]) -> tuple[list[WordMoment], list[WordMoment]]:
    """(words that were missing, false friends): a look-alike is a mistake, not a missing word.

    Example: `split_by_kind([postpone_code_switch, pretend_look_alike])` puts one in each.
    """
    wrong = [moment for moment in moments if moment.reason is Reason.LOOK_ALIKE]
    missing = [moment for moment in moments if moment.reason is not Reason.LOOK_ALIKE]
    return missing, wrong
