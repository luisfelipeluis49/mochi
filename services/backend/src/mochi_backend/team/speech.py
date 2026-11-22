"""What a team gets wrong and what had to be explained to it. Pure functions; numbers only.

Both come from things that hold sentences (a person's report, the stored transcript), and
neither result carries one: an administrator sees that two people mix up verb tenses, never who
and never what they said (AGENTS product rule 3).
"""

from collections.abc import Iterable

from mochi_contracts import (
    ConversationReport,
    ExplainedTerm,
    MarkKind,
    MistakeCount,
    MistakeKind,
    MistakeTopic,
    TranscriptMark,
    Utterance,
)

# A kind of mistake one person makes points at that person; one that two people make points at
# the other one for whichever of the two is looking (an administrator knows their own mistakes).
MISTAKE_MIN_PEOPLE = 3
EXPLAINING = (MarkKind.IDIOM, MarkKind.TECHNICAL_TERM)


def mistakes_in(
    reports: Iterable[ConversationReport], min_people: int = 1, top: int = 10
) -> list[MistakeCount]:
    """The kinds of mistake at least three people made (or `min_people`, when that is more),
    the ones most people share first.

    Example: Ana, Ben and Caio got verb tenses wrong 5, 2 and 1 times -> verb_tense, people 3,
    times 8. A mistake only Ana and Ben made is not listed.
    """
    people: dict[tuple[MistakeTopic, MistakeKind], set[str]] = {}
    times: dict[tuple[MistakeTopic, MistakeKind], int] = {}
    for report in reports:
        for mistake in report.mistakes:
            key = (mistake.topic, mistake.kind)
            people.setdefault(key, set()).add(report.user_id)
            times[key] = times.get(key, 0) + mistake.count
    counts = [
        MistakeCount(topic=topic, kind=kind, people=len(who), times=times[(topic, kind)])
        for (topic, kind), who in people.items()
        if len(who) >= max(min_people, MISTAKE_MIN_PEOPLE)
    ]
    return sorted(counts, key=lambda c: (-c.people, -c.times, c.topic.value, c.kind.value))[:top]


def _term(marks: list[tuple[TranscriptMark, str]]) -> ExplainedTerm:
    newest, at = max(marks, key=lambda pair: pair[1])
    return ExplainedTerm(
        expression=newest.text, meaning=newest.gloss, kind=newest.kind, times=len(marks), last_at=at
    )


def explained_in(said: Iterable[Utterance], top: int = 10) -> list[ExplainedTerm]:
    """The idioms and technical terms explained in the team's meetings, the most frequent first.

    Example: "circle back" explained in three meetings -> times 3. Who said it is not kept.
    """
    grouped: dict[tuple[str, MarkKind], list[tuple[TranscriptMark, str]]] = {}
    found = [(mark, s.at) for s in said for mark in s.marks if mark.kind in EXPLAINING]
    for mark, at in found:
        grouped.setdefault((mark.text.lower(), mark.kind), []).append((mark, at))
    terms = [_term(marks) for marks in grouped.values()]
    return sorted(terms, key=lambda term: (-term.times, term.expression.lower()))[:top]
