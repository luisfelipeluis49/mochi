"""Builders for contexts, turns and hints shared by the tests."""

from datetime import timedelta

from mochi_backend.platform.clock import iso_z
from mochi_contracts import (
    Hint,
    Language,
    Participant,
    Reason,
    SessionContext,
    SessionMode,
    Turn,
)
from tests.fakes.fake_clock import START

ANA = Participant(
    user_id="ana", comfortable_languages=[Language.PT_BR], target_language=Language.EN
)
BEN = Participant(
    user_id="ben", comfortable_languages=[Language.EN], target_language=Language.PT_BR
)


def make_context(
    *,
    participants: list[Participant] | None = None,
    turns: list[Turn] | None = None,
    hints: list[Hint] | None = None,
    mode: SessionMode = SessionMode.MEETING,
) -> SessionContext:
    """A demo SessionContext (Ana learns English, Ben learns Portuguese, focus en)."""
    people = participants if participants is not None else [ANA, BEN]
    return SessionContext(
        session_id="demo",
        mode=mode,
        focus=Language.EN,
        participants=people,
        recent_turns=turns or [],
        recent_hints=hints or [],
        learning_events={p.user_id: [] for p in people},
    )


def make_turn(text: str, seconds: float = 0.0, name: str = "seg") -> Turn:
    """A turn received `seconds` after the test epoch."""
    at = START + timedelta(seconds=seconds)
    return Turn(segment_id=f"{name}_{seconds:g}", text=text, received_at=iso_z(at))


def make_hint(created_at_seconds: float, ttl_seconds: float = 8.0) -> Hint:
    """A hint created `created_at_seconds` after the epoch (expires `ttl` later)."""
    created = START + timedelta(seconds=created_at_seconds)
    return Hint(
        hint_id=f"hint_{created_at_seconds:g}",
        target_user_id="ana",
        target_language=Language.EN,
        expression="postpone",
        meaning="adiar",
        example=None,
        reason=Reason.CODE_SWITCH,
        expires_at=iso_z(created + timedelta(seconds=ttl_seconds)),
    )
