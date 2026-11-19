"""Who receives which event (AGENTS 6.2). Pure functions: no I/O, one test per table row."""

from dataclasses import dataclass
from typing import Literal

from mochi_contracts import (
    EventPayload,
    EventType,
    Hint,
    LearningEvent,
)

TargetKind = Literal["mobile", "home", "audience"]


@dataclass(frozen=True)
class ConnectionTarget:
    """What a connection asked to be: a person's phone, Mochi's own screen, or the projector."""

    kind: TargetKind
    user_id: str | None = None
    device_id: str | None = None


def is_recipient(
    event_type: EventType, payload: EventPayload, target: ConnectionTarget, hint_user: str | None
) -> bool:
    """True when `target` should get this event.

    `hint_user` is the target user of the hint an event refers to (None = shown to everyone).
    Example: `hint.created` for Ana goes to Home, Audience and Ana's phone, not Ben's.
    """
    if event_type is EventType.ACTIVITY_PRIVATE_PROMPT:
        return target.kind == "home"
    if event_type in (EventType.LEARNING_EVENT_CREATED, EventType.LEARNING_EVENT_UPDATED):
        return _owner_only(payload, target)
    if event_type in (EventType.HINT_CREATED, EventType.HINT_CLEARED):
        return _hint_audience(hint_user, target)
    return True


def _owner_only(payload: EventPayload, target: ConnectionTarget) -> bool:
    if not isinstance(payload, LearningEvent) or payload.user_id is None:
        return False  # a learning event with no user is stored but shown to nobody
    return target.kind == "mobile" and target.user_id == payload.user_id


def _hint_audience(hint_user: str | None, target: ConnectionTarget) -> bool:
    if target.kind != "mobile":
        return True
    return hint_user is None or target.user_id == hint_user


def hint_user_of(payload: EventPayload) -> str | None:
    """The target user of a Hint payload, else None."""
    return payload.target_user_id if isinstance(payload, Hint) else None
