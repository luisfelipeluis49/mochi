"""Who receives which event (AGENTS 6.2). Pure functions: no I/O, one test per table row."""

from dataclasses import dataclass
from typing import Literal

from mochi_backend.gateway.roster import SESSION_ID
from mochi_contracts import (
    ConversationReport,
    EventPayload,
    EventType,
    Hint,
    LearningEvent,
    SuggestedPhrase,
)

TargetKind = Literal["mobile", "home", "audience", "glasses"]
# Events that belong to one person: their phone gets them, in whichever session it follows.
# (`transcript.line` is the opposite: everyone in that session, see `is_recipient`.)
# A hint and what follows from it go to the same screens: Home, Audience, and the phone (and
# glasses) of the person it is for. The suggested sentence is one of them (D-59).
HINT_EVENTS = (EventType.HINT_CREATED, EventType.HINT_CLEARED, EventType.PHRASE_SUGGESTED)
PERSONAL_EVENTS = (
    EventType.LEARNING_EVENT_CREATED,
    EventType.LEARNING_EVENT_UPDATED,
    EventType.CONVERSATION_REPORT_CREATED,
)


@dataclass(frozen=True)
class ConnectionTarget:
    """What a connection asked to be: a phone, Mochi's screen, the projector or AR glasses."""

    kind: TargetKind
    user_id: str | None = None
    device_id: str | None = None
    session_id: str = SESSION_ID  # the session it follows (Mochi's own screen: the device's)


def is_recipient(
    event_type: EventType, payload: EventPayload, target: ConnectionTarget, hint_user: str | None
) -> bool:
    """True when `target` should get this event.

    `hint_user` is the target user of the hint an event refers to (None = shown to everyone).
    Example: `hint.created` for Ana goes to Home, Audience and Ana's phone, not Ben's.
    `transcript.line` goes to every screen of the session (the people there heard the
    sentence), and `conversation.report.created` to its person's phone alone.
    """
    if target.kind == "glasses":
        return _glasses_recipient(event_type, target, hint_user)
    if event_type in PERSONAL_EVENTS:
        return _owner_only(payload, target)
    if event_type in HINT_EVENTS:
        return _hint_audience(hint_user, target)
    return True


def _glasses_recipient(
    event_type: EventType, target: ConnectionTarget, hint_user: str | None
) -> bool:
    """AR glasses (AGENTS 6.6, proposed): session state and the wearer's hints, nothing else."""
    if event_type is EventType.SESSION_STATE_CHANGED:
        return True
    if event_type in HINT_EVENTS:
        return hint_user is None or hint_user == target.user_id
    return False


def _owner_only(payload: EventPayload, target: ConnectionTarget) -> bool:
    if not isinstance(payload, LearningEvent | ConversationReport) or payload.user_id is None:
        return False  # a learning event with no user is stored but shown to nobody
    return target.kind == "mobile" and target.user_id == payload.user_id


def _hint_audience(hint_user: str | None, target: ConnectionTarget) -> bool:
    if target.kind != "mobile":
        return True
    return hint_user is None or target.user_id == hint_user


def hint_user_of(payload: EventPayload) -> str | None:
    """The target user of a Hint (or of the sentence suggested after it), else None."""
    return payload.target_user_id if isinstance(payload, Hint | SuggestedPhrase) else None
