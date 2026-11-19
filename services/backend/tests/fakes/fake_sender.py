"""A fake WebSocket client and a recording logger."""

from collections.abc import Mapping

from mochi_backend.platform.json_logging import JsonScalar
from mochi_contracts import Envelope


class FakeSender:
    """Implements the hub's `Sender`. Keeps every message it was sent."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.broken = False

    async def send_text(self, text: str) -> None:
        """Record the message; raises ConnectionError once `broken` is set."""
        if self.broken:
            raise ConnectionError("client gone")
        self.texts.append(text)

    @property
    def events(self) -> list[Envelope]:
        """Everything received, parsed back into envelopes."""
        return [Envelope.model_validate_json(t) for t in self.texts]

    def types(self) -> list[str]:
        """Event type names in arrival order."""
        return [e.type.value for e in self.events]


class FakeEventLogger:
    """Implements `EventLogger`; `lines` holds (event, fields)."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, Mapping[str, JsonScalar]]] = []

    def log(self, event: str, fields: Mapping[str, JsonScalar]) -> None:
        """Record one log line."""
        self.lines.append((event, dict(fields)))

    def names(self) -> list[str]:
        """Event names logged so far."""
        return [name for name, _ in self.lines]
