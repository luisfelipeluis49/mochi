"""Payload models from AGENTS.md sections 6.2 and 6.5. Field names are the contract."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from mochi_contracts.enums import (
    DecisionKind,
    GameState,
    Language,
    LearningState,
    Reason,
    RoundResult,
    SessionMode,
    SessionStatus,
    SpeakReason,
    WordSource,
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


class Hint(ContractModel):
    """One word or short expression shown to help a stuck speaker."""

    hint_id: str
    target_user_id: str | None
    target_language: Language
    expression: str
    meaning: str | None
    example: str | None
    reason: Reason
    expires_at: IsoTimestamp


class HintCleared(ContractModel):
    """Payload of `hint.cleared`."""

    hint_id: str


class Activity(ContractModel):
    """Payload of `activity.state.changed`. Never carries the secret word while active.

    PROPOSAL: the round fields are nullable so an IDLE state can be published
    (AGENTS 6.2 only shows an active example). See docs/DECISIONS.md D-03.
    """

    activity_id: Literal["describe_and_guess"]
    round_id: str | None
    state: GameState
    describer_user_id: str | None
    guesser_user_id: str | None
    public_instruction: str | None
    result: RoundResult | None
    revealed_word: str | None
    word_source: WordSource | None


class PrivatePrompt(ContractModel):
    """Payload of `activity.private_prompt`. Delivered to the Home view only."""

    round_id: str
    describer_user_id: str
    secret_word: str
    source_learning_event_id: str | None


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
    """One finished transcribed sentence. No speaker and no language (AGENTS 6.5)."""

    segment_id: str
    text: str
    received_at: IsoTimestamp


class Participant(ContractModel):
    """One of the two people in the session."""

    user_id: str
    comfortable_languages: list[Language]
    target_language: Language


class SessionContext(ContractModel):
    """Everything `decide()` and `handle()` may look at."""

    session_id: str
    mode: SessionMode
    focus: Language
    participants: list[Participant]
    recent_turns: list[Turn]
    recent_hints: list[Hint]
    activity: Activity | None
    learning_events: dict[str, list[LearningEvent]]


class Decision(ContractModel):
    """Result of `decide()`. IGNORE: no hint, no speak. SPEAK: speak set, hint optional."""

    decision: DecisionKind
    hint: Hint | None
    speak: Speak | None
    learning_events: list[LearningEvent]


class ActivityCommand(ContractModel):
    """PROVISIONAL (AGENTS 6.5 leaves this open): start a round, or report its result."""

    type: Literal["start", "result"]
    result: RoundResult | None


class ActivityResult(ContractModel):
    """PROVISIONAL: the new round state plus what the gateway must publish."""

    activity: Activity
    private_prompt: PrivatePrompt | None
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
