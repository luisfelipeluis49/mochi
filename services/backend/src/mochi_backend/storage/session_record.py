"""One finished web session of one person (DECISIONS D-42). Gateway and storage share this model.

Proposed to move to `packages/contracts` (Matheus) in v0.5; until then it lives here, so the storage
port can use it without importing `gateway`.
"""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from mochi_backend.platform.clock import iso_z


class SessionRecord(BaseModel):
    """`GET /api/users/{user_id}/sessions` returns these, newest first by `ended_at`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str
    session_id: str
    user_id: str
    started_at: str  # ISO-8601 UTC with milliseconds and Z, like every event timestamp
    ended_at: str
    minutes: float
    hint_count: int
    learning_event_ids: list[str]


@dataclass(frozen=True)
class SessionTally:
    """What a running session counted for its record."""

    user_id: str
    started_at: datetime
    hint_count: int
    learning_event_ids: list[str]


def build_record(
    record_id: str, session_id: str, tally: SessionTally, ended_at: datetime
) -> SessionRecord:
    """The record of a session that ran from `tally.started_at` to `ended_at`.

    `minutes` is the length rounded to one decimal place; ids keep their first order, once each.
    Example: 750 seconds apart gives `minutes == 12.5`.
    """
    return SessionRecord(
        record_id=record_id,
        session_id=session_id,
        user_id=tally.user_id,
        started_at=iso_z(tally.started_at),
        ended_at=iso_z(ended_at),
        minutes=round((ended_at - tally.started_at).total_seconds() / 60, 1),
        hint_count=tally.hint_count,
        learning_event_ids=list(dict.fromkeys(tally.learning_event_ids)),
    )
