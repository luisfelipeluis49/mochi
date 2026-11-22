"""What is worked out once a session has stopped, from all of it (DECISIONS D-54, D-55).

Two things, both for a person's own page and neither shown in the meeting: the saved words they
used on their own, and a report of what was wrong in what they said. They wait for Stop because
only then is it settled who said each sentence, and because nothing here is in a hurry.
"""

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mochi_backend.gateway.core import GatewayCore
from mochi_backend.platform.clock import iso_z
from mochi_backend.platform.scheduler import Scheduler
from mochi_backend.team.ledger import TeamLedger
from mochi_contracts import (
    ConversationReport,
    EventType,
    LearningEvent,
    NeededWord,
    Participant,
    SessionMode,
    SessionRecord,
    SpokenSentence,
    Utterance,
    WordMoment,
)

WORDS_PER_MINUTE = 130  # of talk at work; the device's own timing is not kept per sentence
SaveWords = Callable[[list[LearningEvent]], Awaitable[None]]


@dataclass(frozen=True)
class ReportRules:
    """When a report is written. `min_sentences`: fewer than this is too little to judge."""

    enabled: bool = True
    min_sentences: int = 3
    timeout_seconds: float = 60.0


def needed_words(moments: list[WordMoment], own: set[str]) -> list[NeededWord]:
    """One entry per word a person needed in a session: how often, and what they said instead.

    `own`: that person's own sentences. A word can be theirs although someone else's voice said
    the sentence (AGENTS 7.3, rule 2), and another person's sentence never goes into a report.
    Example: "postpone" needed twice -> `NeededWord(expression="postpone", times=2, ...)`.
    """
    times = Counter(moment.expression.lower() for moment in moments)
    first: dict[str, WordMoment] = {}
    for moment in moments:
        first.setdefault(moment.expression.lower(), moment)
    return [
        NeededWord(
            expression=moment.expression,
            meaning=moment.meaning,
            said_instead=moment.heard if moment.heard in own else None,
            times=times[key],
        )
        for key, moment in first.items()
    ]


def spoken_minutes(said: list[Utterance]) -> float:
    """About how long these sentences took to say, to one decimal. Example: 260 words -> 2.0."""
    words = sum(len(sentence.text.split()) for sentence in said)
    return round(words / WORDS_PER_MINUTE, 1)


class AfterSession:
    """Example: `after.begin(record)` right after Stop; the work runs in the background."""

    def __init__(
        self, core: GatewayCore, ledger: TeamLedger, scheduler: Scheduler, rules: ReportRules
    ) -> None:
        self._core = core
        self._ledger = ledger
        self._scheduler = scheduler
        self._rules = rules
        self._save: SaveWords | None = None

    def saving_with(self, save: SaveWords) -> "AfterSession":
        """How a changed card is stored and published (the turn pipeline's own way)."""
        self._save = save
        return self

    def begin(self, record: SessionRecord, shown: list[str]) -> None:
        """Look back at the session that has just closed, without making Stop wait.

        `shown`: every word that was on a screen during it (`SessionJournal.words_shown`).
        """
        self._scheduler.call_later(0.0, lambda: self.run(record, shown))

    async def run(self, record: SessionRecord, shown: list[str]) -> None:
        """Mark the words used on their own, then write each person's report.

        Example: `await after.run(record, [])` -> Ana's phone gets `conversation.report.created`.
        """
        said = self._ledger.utterances_in(record.record_id)
        mine = self._ledger.moments_of(record.company_id)
        needed = [moment for moment in mine if moment.record_id == record.record_id]
        if record.mode is SessionMode.MEETING and self._save is not None:
            began = record.started_at
            await self._save(self._core.intelligence.used_alone(said, shown, began))
        if self._rules.enabled:
            await self._reports(record, said, needed)

    async def _reports(
        self, record: SessionRecord, said: list[Utterance], needed: list[WordMoment]
    ) -> None:
        people = {p.user_id: p for p in self._core.store.roster.participants()}
        spoke = Counter(sentence.user_id for sentence in said if sentence.user_id in people)
        writing = [
            self._report(
                record,
                people[user or ""],
                [s for s in said if s.user_id == user],
                [m for m in needed if m.user_id == user],
            )
            for user, sentences in spoke.items()
            if sentences >= self._rules.min_sentences
        ]
        for outcome in await asyncio.gather(*writing, return_exceptions=True):
            if isinstance(outcome, BaseException):
                self._core.logger.log("report_failed", {"error": repr(outcome)})

    def _draft(
        self,
        record: SessionRecord,
        person: Participant,
        said: list[Utterance],
        needed: list[WordMoment],
    ) -> ConversationReport:
        return ConversationReport(
            report_id=self._core.ids.new("rep"),
            company_id=record.company_id,
            record_id=record.record_id,
            user_id=person.user_id,
            target_language=person.target_language,
            mode=record.mode,
            started_at=record.started_at,
            ended_at=record.ended_at or iso_z(self._core.clock.now()),
            speaking_minutes=spoken_minutes(said),
            my_sentences=[
                SpokenSentence(utterance_id=s.utterance_id, at=s.at, text=s.text) for s in said
            ],
            mistakes=[],
            unknown_words=needed_words(needed, {sentence.text for sentence in said}),
            strengths=[],
            focus_next=[],
        )

    async def _report(
        self,
        record: SessionRecord,
        person: Participant,
        said: list[Utterance],
        needed: list[WordMoment],
    ) -> None:
        """One person's report: written by the coach, kept, and sent to their phone only."""
        draft = self._draft(record, person, said, needed)
        coached = self._core.intelligence.coach(draft, person)
        report = await asyncio.wait_for(coached, self._rules.timeout_seconds)
        if report is None or self._ledger.record(record.record_id) is None:
            return  # nothing could be said, or the history was reset meanwhile
        self._ledger.keep_report(report)
        await self._core.hub.publish(EventType.CONVERSATION_REPORT_CREATED, report)
        self._core.logger.log(
            "report_written", {"report_id": report.report_id, "mistakes": len(report.mistakes)}
        )
