"""The event envelope (AGENTS 6.1) and the payload each event type carries."""

from typing import Self

from pydantic import model_validator

from mochi_contracts.enums import EventType
from mochi_contracts.models import (
    ContractModel,
    ConversationReport,
    Hint,
    HintCleared,
    IsoTimestamp,
    LearningEvent,
    SessionState,
    Speak,
    TranscriptLine,
)

SCHEMA_VERSION = "0.7"

EventPayload = (
    SessionState | Hint | HintCleared | LearningEvent | Speak | TranscriptLine | ConversationReport
)

PAYLOAD_TYPE_FOR_EVENT: dict[EventType, type[ContractModel]] = {
    EventType.SESSION_STATE_CHANGED: SessionState,
    EventType.HINT_CREATED: Hint,
    EventType.HINT_CLEARED: HintCleared,
    EventType.LEARNING_EVENT_CREATED: LearningEvent,
    EventType.LEARNING_EVENT_UPDATED: LearningEvent,
    EventType.AGENT_SPEAK_REQUESTED: Speak,
    EventType.TRANSCRIPT_LINE: TranscriptLine,
    EventType.CONVERSATION_REPORT_CREATED: ConversationReport,
}


class Envelope(ContractModel):
    """One WebSocket message. Only the gateway hub builds these."""

    schema_version: str
    event_id: str
    type: EventType
    session_id: str
    emitted_at: IsoTimestamp
    sequence: int
    payload: EventPayload

    @model_validator(mode="after")
    def _payload_matches_type(self) -> Self:
        expected = PAYLOAD_TYPE_FOR_EVENT[self.type]
        if not isinstance(self.payload, expected):
            raise ValueError(
                f"event {self.type.value!r} needs a {expected.__name__} payload; "
                f"got {type(self.payload).__name__}"
            )
        return self
