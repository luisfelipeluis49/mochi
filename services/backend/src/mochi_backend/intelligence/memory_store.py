"""Learning events held in memory; an optional sink keeps a durable copy (DECISIONS D-32)."""

from typing import Protocol

from mochi_contracts import LearningEvent


class EventSink(Protocol):
    """Where a durable copy goes. Intelligence only calls it; it opens no connection itself."""

    def save(self, event: LearningEvent) -> None:
        """Keep this event (create, or replace the one with the same id)."""
        ...

    def clear(self) -> None:
        """Forget every event."""
        ...


class MemoryStore:
    """Holds every saved word. Example: `store.apply([event])` then `store.words_for("ana")`.

    Reads are always served from memory. `restored` is what the sink kept before a restart,
    oldest first, so "newest first" still means the newest saved.
    """

    def __init__(
        self, restored: list[LearningEvent] | None = None, sink: EventSink | None = None
    ) -> None:
        self._events: dict[str, LearningEvent] = {e.learning_event_id: e for e in restored or []}
        self._sink = sink

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or replace each event by id; return what is now stored, in input order."""
        for proposal in proposals:
            self._events[proposal.learning_event_id] = proposal
            if self._sink is not None:
                self._sink.save(proposal)
        return [self._events[p.learning_event_id] for p in proposals]

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """That user's events, newest first (events with no user belong to nobody)."""
        mine = [e for e in self._events.values() if e.user_id == user_id]
        return list(reversed(mine))

    def reset(self) -> None:
        """Forget every saved word (and the durable copy)."""
        self._events.clear()
        if self._sink is not None:
            self._sink.clear()
