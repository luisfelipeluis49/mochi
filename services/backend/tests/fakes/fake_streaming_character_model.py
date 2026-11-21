"""A scripted Mochi writing its line in pieces: `FakeStreamingCharacterModel("Hi", "!")`."""

from collections.abc import AsyncGenerator

from mochi_backend.intelligence.character_port import CharacterRequest, CharacterStreamError


class FakeStreamingCharacterModel:
    """Implements `StreamingCharacterModel`. `reply` answers the pieces joined; `stream_reply`
    yields them one by one and, with `fail_after`, breaks off after that many pieces."""

    def __init__(self, *pieces: str, fail_after: int | None = None) -> None:
        self._pieces = list(pieces)
        self._fail_after = fail_after
        self.replied = 0
        self.streamed = 0
        self.closed = False

    async def reply(self, request: CharacterRequest) -> str | None:
        """The whole line at once (the buffered path)."""
        self.replied += 1
        return "".join(self._pieces)

    async def stream_reply(self, request: CharacterRequest) -> AsyncGenerator[str]:
        """The line piece by piece; `CharacterStreamError` after `fail_after` pieces."""
        self.streamed += 1
        try:
            for index, piece in enumerate(self._pieces):
                if index == self._fail_after:
                    raise CharacterStreamError("scripted break")
                yield piece
        finally:
            self.closed = True
