"""Where text goes while it is being written: shared by both halves without either importing the
other. The gateway hands one to intelligence when Mochi's reply may be streamed (DECISIONS D-37).
"""

from typing import Protocol


class TextSink(Protocol):
    """Takes pieces of text in order. Example: `sink.put("Hi")`, then `sink.put(" there!")`."""

    def put(self, text: str) -> None:
        """Take the next piece; it must not block."""
        ...
