"""Finished web sessions, per person (D-42). Read from storage at startup, kept in memory, and each
new record is written through storage, so a backend that spins down keeps them."""

from mochi_backend.storage.port import Storage
from mochi_backend.storage.session_record import SessionRecord

ANSWER_LIMIT = 50


class SessionHistory:
    """Example: `history.add(record)` then `history.for_user("luis-felipe-3f9c1a")`."""

    def __init__(self, storage: Storage, restored: list[SessionRecord]) -> None:
        self._storage = storage
        self._records: list[SessionRecord] = list(restored)

    def add(self, record: SessionRecord) -> None:
        """Keep a new record and save it."""
        self._records.append(record)
        self._storage.save_session(record)

    def for_user(self, user_id: str) -> list[SessionRecord]:
        """This person's records, newest first by `ended_at`, at most 50.

        `ended_at` strings sort as times: they all have the same ISO-8601 Z shape. Two that ended
        at the same moment: the one added last comes first (the sort is stable).
        """
        mine = [record for record in reversed(self._records) if record.user_id == user_id]
        mine.sort(key=lambda record: record.ended_at, reverse=True)
        return mine[:ANSWER_LIMIT]
