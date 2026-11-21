"""Connects the intelligence's `EventSink` to a `Storage` (intelligence never imports storage)."""

from mochi_backend.storage.port import Storage
from mochi_contracts import LearningEvent


class StorageEventSink:
    """Implements `EventSink`. Example: `MemoryStore([], StorageEventSink(storage))`."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def save(self, event: LearningEvent) -> None:
        """Hand the event to storage."""
        self._storage.save_event(event)

    def clear(self) -> None:
        """Delete every stored event."""
        self._storage.clear_events()
