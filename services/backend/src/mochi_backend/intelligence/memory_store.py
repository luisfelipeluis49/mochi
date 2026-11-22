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
        self._events: dict[str, LearningEvent] = {}
        self._by_user: dict[str, dict[str, LearningEvent]] = {}  # each person's, in save order
        self._sink = sink
        for event in restored or []:
            self._keep(event)

    def _keep(self, event: LearningEvent) -> None:
        """Store `event` under its id and in its person's index (a replaced one moves, if its
        person changed). `words_for` runs on every turn, so it must not scan every event."""
        earlier = self._events.get(event.learning_event_id)
        if earlier is not None and earlier.user_id != event.user_id:
            self._by_user.get(earlier.user_id or "", {}).pop(event.learning_event_id, None)
        self._events[event.learning_event_id] = event
        if event.user_id is not None:
            self._by_user.setdefault(event.user_id, {})[event.learning_event_id] = event

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or replace each event by id; return what is now stored, in input order."""
        for proposal in proposals:
            self._keep(proposal)
            if self._sink is not None:
                self._sink.save(proposal)
        return [self._events[p.learning_event_id] for p in proposals]

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """That user's events, newest first (events with no user belong to nobody)."""
        return list(reversed(self._by_user.get(user_id, {}).values()))

    def reset(self) -> None:
        """Forget every saved word (and the durable copy)."""
        self._events.clear()
        self._by_user.clear()
        if self._sink is not None:
            self._sink.clear()
