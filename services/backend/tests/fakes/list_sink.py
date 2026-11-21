"""A `TextSink` that keeps what it was given. Example: `sink = ListSink(); sink.put("Hi")`."""


class ListSink:
    """Implements `platform.text_sink.TextSink`; `pieces` holds every piece in order."""

    def __init__(self) -> None:
        self.pieces: list[str] = []

    def put(self, text: str) -> None:
        """Keep the piece."""
        self.pieces.append(text)
