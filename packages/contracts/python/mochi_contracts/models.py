"""Payload models from AGENTS.md sections 6.2 and 6.5. Field names are the contract."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from mochi_contracts.enums import (
    DecisionKind,
    Language,
    LearningState,
    MarkKind,
    MemberRole,
    MistakeKind,
    MistakeTopic,
    Reason,
    SessionMode,
    SessionStatus,
    SpeakReason,
)

# UTC ISO-8601 with milliseconds, e.g. 2026-11-19T16:00:04.700Z (AGENTS 6.1).
IsoTimestamp = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T[\d:]{8}\.\d{3}Z$")]


class ContractModel(BaseModel):
    """Base: immutable, and an unknown field is an error (no silent contract drift)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionState(ContractModel):
    """Payload of `session.state.changed` (AGENTS calls it Session)."""

    status: SessionStatus
    mode: SessionMode
    focus: Language
    capturing: bool
    participants: list[str]


class HintCandidate(ContractModel):
    """One of up to three plausible words for a hint with no single known answer."""

    expression: str
    meaning: str | None


class Hint(ContractModel):
    """One word or short expression shown to help a stuck speaker.

    PROPOSAL (not yet signed off, see docs/DECISIONS.md): `candidates` and `context` are
    additive and optional. They are set only for a hint with no single known word (reasons
    trails_off, restarts, talks_around): up to three plausible completions instead of one
    guess, plus the sentence they stopped in. Every other reason leaves both `None`, and a
    client that does not know them still shows `expression`/`meaning` as before.
    """

    hint_id: str
    target_user_id: str | None
    target_language: Language
    expression: str
    meaning: str | None
    example: str | None
    reason: Reason
    expires_at: IsoTimestamp
    candidates: list[HintCandidate] | None = None
    context: str | None = None


class SuggestedPhrase(ContractModel):
    """Payload of `phrase.suggested`: the whole sentence a stuck speaker was trying to say, a
    moment after their hint. PROPOSAL (DECISIONS D-59, "one-touch assistance").

    It goes where the hint went. Until `expires_at`, one touch (on Mochi's screen, or
    `POST /api/sessions/{id}/hints/{hint_id}/say`) makes Mochi say `text` aloud, once.
    """

    hint_id: str
    target_user_id: str | None
    language: Language
    text: str
    expires_at: IsoTimestamp


class HintCleared(ContractModel):
    """Payload of `hint.cleared`."""

    hint_id: str


class StateChange(ContractModel):
    """One entry of a learning event's `state_history`."""

    learning_state: LearningState
    at: IsoTimestamp


class LearningEvent(ContractModel):
    """A saved word with its history for one person (a card under My words)."""

    learning_event_id: str
    user_id: str | None
    target_language: Language
    expression: str
    meaning: str | None
    detection_signal: Reason
    hint_id: str | None
    learning_state: LearningState
    state_history: list[StateChange]


class Speak(ContractModel):
    """Payload of `agent.speak.requested`; also the text returned to Agora."""

    text: str
    language: Language
    reason: SpeakReason


class Turn(ContractModel):
    """One finished transcribed sentence. No language; the speaker only when a voice was known.

    PROPOSAL (v0.7, DECISIONS D-44): `speaker_user_id` is the person whose registered voice the
    device recognised while the sentence was said. `None` when nobody was recognised (a phone's
    microphone, an unknown voice), exactly as before.
    """

    segment_id: str
    text: str
    received_at: IsoTimestamp
    speaker_user_id: str | None = None


class Participant(ContractModel):
    """One of the people in the session (a meeting's members, or the one person reviewing)."""

    user_id: str
    comfortable_languages: list[Language]
    target_language: Language


class SessionContext(ContractModel):
    """Everything `decide()` may look at."""

    session_id: str
    mode: SessionMode
    focus: Language
    participants: list[Participant]
    recent_turns: list[Turn]
    recent_hints: list[Hint]
    learning_events: dict[str, list[LearningEvent]]


class Decision(ContractModel):
    """Result of `decide()`. IGNORE: no hint, no speak. SPEAK: speak set, hint optional."""

    decision: DecisionKind
    hint: Hint | None
    speak: Speak | None
    learning_events: list[LearningEvent]


class User(ContractModel):
    """One person Mochi knows. Proposed in v0.5 (stored in the database; see DECISIONS D-32)."""

    user_id: str
    display_name: str
    comfortable_languages: list[Language]
    target_language: Language


VoiceLanguage = Literal["en", "pt"]  # the same two codes as `POST /api/devices/*/voices`


class VoiceProfile(ContractModel):
    """A voice Mochi has learned, as the device-key-protected voices endpoints return it.

    HTTP only: it carries a biometric voiceprint, so it is never sent as a WebSocket event.
    """

    name: str
    user_id: str | None
    language: VoiceLanguage
    voiceprint: list[float] | None
    saved: str | None


class VoiceprintUpload(ContractModel):
    """Body of `PUT /api/devices/{id}/voices/{name}/voiceprint` (device key required)."""

    language: VoiceLanguage
    voiceprint: list[float]
    saved: Annotated[str | None, StringConstraints(max_length=64)]  # a timestamp text


class Company(ContractModel):
    """A company that uses Papear. PROPOSAL (v0.7, DECISIONS D-45)."""

    company_id: str
    name: str


class Member(ContractModel):
    """One person's place in a company. `admin` may open the team view; `team` is free text."""

    company_id: str
    user_id: str
    role: MemberRole
    team: str | None = None


class SpeakingShare(ContractModel):
    """How much one person said in a session. `user_id` None: voices nobody had registered."""

    user_id: str | None
    turns: int
    words: int


class SessionRecord(ContractModel):
    """One session from Start to Stop, kept for the analytics (its sentences are Utterances).

    `ended_at` is None while it runs. `speaking` counts finished sentences per recognised voice.
    """

    record_id: str
    company_id: str
    session_id: str
    mode: SessionMode
    started_at: IsoTimestamp
    ended_at: IsoTimestamp | None
    participants: list[str]
    speaking: list[SpeakingShare]


class TranscriptMark(ContractModel):
    """Something Mochi noticed in a sentence, shown with it in the live transcript.

    `text` is the part of the sentence it is about. `gloss` is what to read next to it: for a
    code switch the word in the language being spoken ("adiar" -> "postpone"), for an idiom or a
    technical term what it means in the other language ("circle back" -> "voltar ao assunto").
    `plain`, for an idiom or a term, says the same in everyday words of the language spoken.
    """

    kind: MarkKind
    text: str
    gloss: str | None
    plain: str | None = None


class Utterance(ContractModel):
    """One finished sentence of a session and who said it. PROPOSAL (v0.7, DECISIONS D-46).

    `user_id` is the person whose registered voice said it; None when no known voice did, or
    when it could not be told. It goes to that person's own page only, never to the team view.
    """

    utterance_id: str
    company_id: str
    record_id: str | None
    user_id: str | None
    text: str
    at: IsoTimestamp
    marks: list[TranscriptMark] = []  # what Mochi noticed in it (D-51 to D-53)


class HeardPhrase(ContractModel):
    """A stretch of speech between two pauses, as the device heard it: who, how long, how long ago.

    Sent with the device status (DECISIONS D-46). `speaker` is the name the voice was registered
    under, None when it was nobody the device knows or it could not tell. `ago_ms`: how long
    before the report the stretch ended.
    """

    speaker: Annotated[str, StringConstraints(max_length=40)] | None
    seconds: float
    ago_ms: int


class TranscriptLine(ContractModel):
    """Payload of `transcript.line`: one finished sentence, sent as it is said (D-51).

    Sent to the people in that session, who all heard it; it is not what is stored (that is the
    `Utterance`, which only its speaker may read). The same `utterance_id` is sent again when
    something was noticed in the sentence (`marks`): a screen replaces the line it has.
    `user_id` is the person whose registered voice said it, None when no known voice did.
    """

    utterance_id: str
    user_id: str | None
    text: str
    at: IsoTimestamp
    marks: list[TranscriptMark] = []


class SpokenSentence(ContractModel):
    """One sentence a person said, in a report of their own. `better`: the sentence put right,
    None when nothing was wrong with it; `topic`: the group its mistake belongs to."""

    utterance_id: str
    at: IsoTimestamp
    text: str
    better: str | None = None
    topic: MistakeTopic | None = None


class Mistake(ContractModel):
    """A mistake a person made in a session: one real example, and how often its kind came up.

    `explanation` is one short sentence in the language the person is at home in.
    """

    kind: MistakeKind
    topic: MistakeTopic
    said: str
    better: str
    explanation: str | None
    count: int


class NeededWord(ContractModel):
    """A word the person needed in the session (from its word moments), and what they said."""

    expression: str
    meaning: str | None
    said_instead: str | None
    times: int


class ConversationReport(ContractModel):
    """Payload of `conversation.report.created`: what Mochi noticed in ONE person's speech in
    ONE session, written after it stopped. PROPOSAL (DECISIONS D-54).

    It is that person's alone: their phone gets the event, and only they may read
    `GET /api/users/{id}/reports`. `my_sentences` holds what their registered voice said, never
    what others said. Nothing of it is shown during the meeting. `strengths` and `focus_next`
    are short lines in the language the person is at home in.
    """

    report_id: str
    company_id: str
    record_id: str | None
    user_id: str
    target_language: Language
    mode: SessionMode
    started_at: IsoTimestamp
    ended_at: IsoTimestamp
    speaking_minutes: float
    my_sentences: list[SpokenSentence]
    mistakes: list[Mistake]
    unknown_words: list[NeededWord]
    strengths: list[str]
    focus_next: list[str]


class WordMoment(ContractModel):
    """One time someone needed a word: a row per hint shown or answer spoken.

    A LearningEvent is one card per person and word; this is every occurrence, so "needed five
    times this month" can be counted. `heard` is the person's own sentence; it goes to their own
    page only, never into the team view.
    """

    moment_id: str
    company_id: str
    record_id: str | None
    user_id: str | None
    expression: str
    meaning: str | None
    target_language: Language
    reason: Reason
    at: IsoTimestamp
    heard: str | None = None


class TeamTotals(ContractModel):
    """The headline numbers of a team view, for its period."""

    members: int
    active_members: int  # took part in a session or needed a word in the period
    meetings: int
    reviews: int
    meeting_minutes: int
    moments: int  # times someone needed a word
    words: int  # different expressions needed


class LearningFunnel(ContractModel):
    """How many saved words got at least this far (every card of every member, all time)."""

    discovered: int
    assisted: int
    reinforced: int
    used_independently: int


class ReasonCount(ContractModel):
    """How often people got stuck in one way. `share` is of all moments, 0 to 1."""

    reason: Reason
    times: int
    share: float


class SharedGap(ContractModel):
    """An expression the team needed: by how many people, how often, and why. Never by whom."""

    expression: str
    meaning: str | None
    target_language: Language
    people: int
    times: int
    reasons: list[ReasonCount]
    last_at: IsoTimestamp


class MistakeCount(ContractModel):
    """A kind of mistake the team makes: by how many people and how often. Never a sentence."""

    topic: MistakeTopic
    kind: MistakeKind
    people: int
    times: int


class ExplainedTerm(ContractModel):
    """An idiom or technical term Mochi explained in the team's meetings, and how often.

    It says what the team's own way of talking is hard on, not who did not understand it.
    """

    expression: str
    meaning: str | None
    kind: MarkKind
    times: int
    last_at: IsoTimestamp


class WeekActivity(ContractModel):
    """One week of the period. `week_start` is its Monday, e.g. "2026-11-16"."""

    week_start: str
    meetings: int
    moments: int
    people: int
    new_words: int


class MemberProgress(ContractModel):
    """One member's numbers for an administrator: counts only, no words and no sentences."""

    user_id: str
    display_name: str
    role: MemberRole
    team: str | None
    target_language: Language
    meetings: int
    reviews: int
    speaking_turns: int
    moments: int
    words: int  # saved cards, all time
    assisted: int  # of those, used with help or better
    reinforced: int  # of those, recalled in a review or better
    last_active_at: IsoTimestamp | None


HighlightKind = Literal[
    "shared_gap",  # the expression the most people needed
    "repeated_gap",  # needed again and again, and not yet used by anyone afterwards
    "false_friend",  # the look-alike mistake made most often
    "words_sticking",  # share of saved words that people went on to use
    "review_backlog",  # saved words nobody has reviewed yet
]


class Highlight(ContractModel):
    """One thing worth an administrator's attention. The screen writes the sentence from it."""

    kind: HighlightKind
    expression: str | None = None
    people: int | None = None
    times: int | None = None
    share: float | None = None


class TeamInsights(ContractModel):
    """Response of `GET /api/companies/{id}/insights`: the team view (DECISIONS D-45).

    Aggregated from every member's learning data. Expressions carry how many people needed
    them, never who; per-member rows carry counts only.
    """

    company: Company
    generated_at: IsoTimestamp
    period_days: int
    totals: TeamTotals
    funnel: LearningFunnel
    signals: list[ReasonCount]
    shared_gaps: list[SharedGap]
    false_friends: list[SharedGap]
    mistakes: list[MistakeCount]  # from the members' conversation reports (D-54)
    explained: list[ExplainedTerm]  # idioms and technical terms explained to the room (D-53)
    weekly: list[WeekActivity]
    members: list[MemberProgress]
    highlights: list[Highlight]


class TeamMember(ContractModel):
    """A member as the company routes return and accept it: the person plus their role."""

    user: User
    role: MemberRole
    team: str | None = None
