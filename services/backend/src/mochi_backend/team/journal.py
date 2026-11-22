"""Writes one session into the ledger: when it ran, what was said and by whom, who needed a word.

A sentence gets its speaker when it arrives, from what the device has said so far; when the
session ends every sentence is looked at again with everything the device said (a report can
arrive after its sentence), and the record's speaking counts are made from that.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from mochi_backend.platform.clock import Clock, iso_z, parse_iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.team.ledger import TeamLedger
from mochi_backend.team.timeline import ARRIVAL_LAG, Phrase, SpeakerTimeline
from mochi_contracts import (
    Hint,
    SessionMode,
    SessionRecord,
    SpeakingShare,
    TranscriptMark,
    Turn,
    Utterance,
    WordMoment,
)

# "Can you say it again?" shows the same word a second time: still one moment.
REPEAT_WINDOW = timedelta(seconds=60)


@dataclass(frozen=True)
class _Said:
    """A sentence and the stretch of time its speech fell in (for the second look at the end)."""

    utterance_id: str
    after: datetime
    until: datetime
    fallback: str | None  # the speaker it was given when the device had said nothing


class SessionJournal:
    """One per session. Example: `journal.begin("demo", SessionMode.MEETING, ["ana", "ben"])`."""

    def __init__(self, ledger: TeamLedger, clock: Clock, ids: IdGenerator, company_id: str) -> None:
        self._ledger = ledger
        self._clock = clock
        self._ids = ids
        self._company_id = company_id
        self._record: SessionRecord | None = None
        self._last: dict[tuple[str | None, str], WordMoment] = {}
        self._timeline = SpeakerTimeline()
        self._cut = clock.now()  # speech up to here belongs to sentences already kept
        self._said: list[_Said] = []
        self._shown: set[str] = set()  # every word a screen showed in the session, lower case

    def words_shown(self) -> list[str]:
        """Every word that was on a screen in the session that is open, or that just ended: each
        hint's word and the other words shown with it. Example: `["postpone", "raincoat"]`."""
        return sorted(self._shown)

    def begin(self, session_id: str, mode: SessionMode, participants: list[str]) -> None:
        """A session started: open its record (an unfinished one is closed first)."""
        self.end()
        self._timeline, self._cut, self._said = SpeakerTimeline(), self._clock.now(), []
        self._shown = set()
        self._record = SessionRecord(
            record_id=self._ids.new("rec"),
            company_id=self._company_id,
            session_id=session_id,
            mode=mode,
            started_at=iso_z(self._clock.now()),
            ended_at=None,
            participants=participants,
            speaking=[],
        )
        self._ledger.keep_record(self._record)

    def phrase(self, user_id: str | None, seconds: float, ended_at: datetime) -> None:
        """The device heard a stretch of speech. Example: `journal.phrase("ana", 2.4, at)`."""
        if self._record is not None:
            self._timeline.add(Phrase(user_id, seconds, ended_at))

    def reports_voices(self) -> bool:
        """True once the device has reported a stretch of speech in this session (it can tell
        voices apart; a phone's microphone, or an older device, never does)."""
        return len(self._timeline) > 0

    def speaker_of(self, heard_at: datetime, sticky: str | None) -> str | None:
        """Whose the sentence that arrived at `heard_at` is, from the stretches heard since the
        sentence before. `sticky`: the speaker last named, used only with a device that reports
        no stretches at all (an older one), or in a review.

        Example: Ana spoke 2 s just before -> "ana".
        """
        if len(self._timeline) == 0:
            return sticky
        return self._timeline.between(self._cut, heard_at - ARRIVAL_LAG).user_id

    def heard(self, turn: Turn, marks: list[TranscriptMark] | None = None) -> None:
        """Keep one finished sentence with the speaker it was given (`turn.speaker_user_id`),
        and what was noticed in it (`marks`: a code switch)."""
        if self._record is None:
            return
        until = parse_iso_z(turn.received_at) - ARRIVAL_LAG
        sticky = turn.speaker_user_id if len(self._timeline) == 0 else None
        self._said.append(_Said(turn.segment_id, self._cut, until, sticky))
        self._cut = max(self._cut, until)
        self._ledger.keep_utterance(
            Utterance(
                utterance_id=turn.segment_id,
                company_id=self._company_id,
                record_id=self._record.record_id,
                user_id=turn.speaker_user_id,
                text=turn.text,
                at=turn.received_at,
                marks=marks or [],
            )
        )

    def noticed(self, utterance_id: str, mark: TranscriptMark) -> Utterance | None:
        """Something was noticed in a sentence after it was kept (an idiom explained): keep it
        with the sentence. None when the sentence is not of the open session.

        Example: `journal.noticed("seg_009", mark)` -> the sentence, with the mark added.
        """
        kept = self._ledger.utterance(utterance_id)
        if self._record is None or kept is None or kept.record_id != self._record.record_id:
            return None
        marked = kept.model_copy(update={"marks": [*kept.marks, mark]})
        self._ledger.keep_utterance(marked)
        return marked

    def needed(self, hint: Hint, turn: Turn) -> WordMoment | None:
        """Someone needed a word: keep the moment. None when it repeats the one just kept."""
        others = [candidate.expression for candidate in hint.candidates or []]
        self._shown |= {word.lower() for word in (hint.expression, *others)}
        key = (hint.target_user_id, hint.expression.lower())
        before = self._last.get(key)
        now = self._clock.now()
        if before is not None and now - parse_iso_z(before.at) <= REPEAT_WINDOW:
            return None
        moment = self._moment(hint, turn, iso_z(now))
        self._last[key] = moment
        self._ledger.keep_moment(moment)
        return moment

    def _moment(self, hint: Hint, turn: Turn, at: str) -> WordMoment:
        return WordMoment(
            moment_id=self._ids.new("mom"),
            company_id=self._company_id,
            record_id=self._record.record_id if self._record else None,
            user_id=hint.target_user_id,
            expression=hint.expression,
            meaning=hint.meaning,
            target_language=hint.target_language,
            reason=hint.reason,
            at=at,
            heard=turn.text,
        )

    def transcript(self) -> list[Utterance]:
        """The open session's sentences so far, in order (empty when none is open)."""
        if self._record is None:
            return []
        return self._ledger.utterances_in(self._record.record_id)

    def _final_speaker(self, utterance: Utterance, said: _Said | None) -> str | None:
        """Who said it, with everything the device reported by now (also after the sentence)."""
        if said is None or len(self._timeline) == 0:
            return utterance.user_id
        verdict = self._timeline.between(said.after, said.until)
        return verdict.user_id if verdict.heard else said.fallback

    def _second_look(self, record_id: str) -> list[Utterance]:
        """Every sentence of the session with its final speaker: a stretch the device reported
        after its sentence had arrived is counted now."""
        windows = {said.utterance_id: said for said in self._said}
        final: list[Utterance] = []
        for utterance in self._ledger.utterances_in(record_id):
            who = self._final_speaker(utterance, windows.get(utterance.utterance_id))
            settled = utterance.model_copy(update={"user_id": who})
            if settled != utterance:
                self._ledger.keep_utterance(settled)
            final.append(settled)
        return final

    def end(self) -> SessionRecord | None:
        """The session stopped: close its record with who said how much, and return it (None
        when none was open). Its sentences have their final speakers from here on."""
        record, self._record = self._record, None
        self._last = {}
        if record is None:
            return None
        spoken: dict[str | None, tuple[int, int]] = {}
        for utterance in self._second_look(record.record_id):
            sentences, words = spoken.get(utterance.user_id, (0, 0))
            spoken[utterance.user_id] = (sentences + 1, words + len(utterance.text.split()))
        shares = [
            SpeakingShare(user_id=user, turns=sentences, words=words)
            for user, (sentences, words) in spoken.items()
        ]
        closed = record.model_copy(
            update={"ended_at": iso_z(self._clock.now()), "speaking": shares}
        )
        self._ledger.keep_record(closed)
        return closed

    def forget(self) -> None:
        """Demo reset: drop what was kept so far; a running session keeps counting from here."""
        self._last, self._said, self._shown = {}, [], set()
        self._timeline, self._cut = SpeakerTimeline(), self._clock.now()
