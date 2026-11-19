"""In-memory learning events (AGENTS 8: no database)."""

from mochi_contracts import LearningEvent


class MemoryStore:
    """Holds every saved word. Example: `store.apply([event])` then `store.words_for("ana")`."""

    def __init__(self) -> None:
        self._events: dict[str, LearningEvent] = {}

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or replace each event by id; return what is now stored, in input order."""
        for proposal in proposals:
            self._events[proposal.learning_event_id] = proposal
        return [self._events[p.learning_event_id] for p in proposals]

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """That user's events, newest first (events with no user belong to nobody)."""
        mine = [e for e in self._events.values() if e.user_id == user_id]
        return list(reversed(mine))

    def reset(self) -> None:
        """Forget every saved word."""
        self._events.clear()
