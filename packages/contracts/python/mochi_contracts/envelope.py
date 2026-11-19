"""The event envelope (AGENTS 6.1) and the payload each event type carries."""

from typing import Self

from pydantic import model_validator

from mochi_contracts.enums import EventType
from mochi_contracts.models import (
    Activity,
    ContractModel,
    Hint,
    HintCleared,
    IsoTimestamp,
    LearningEvent,
    PrivatePrompt,
    SessionState,
    Speak,
)

SCHEMA_VERSION = "0.4"

EventPayload = SessionState | Hint | HintCleared | Activity | PrivatePrompt | LearningEvent | Speak

PAYLOAD_TYPE_FOR_EVENT: dict[EventType, type[ContractModel]] = {
    EventType.SESSION_STATE_CHANGED: SessionState,
    EventType.HINT_CREATED: Hint,
    EventType.HINT_CLEARED: HintCleared,
    EventType.ACTIVITY_STATE_CHANGED: Activity,
    EventType.ACTIVITY_PRIVATE_PROMPT: PrivatePrompt,
    EventType.LEARNING_EVENT_CREATED: LearningEvent,
    EventType.LEARNING_EVENT_UPDATED: LearningEvent,
    EventType.AGENT_SPEAK_REQUESTED: Speak,
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
