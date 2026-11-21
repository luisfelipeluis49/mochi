"""Mochi's free-chat line while the model writes it: passed on piece by piece (DECISIONS D-37).

Intelligence owns what the words mean: `[quiet]` anywhere means Mochi says nothing, so the stream
stops there; `[play]` starts a round whose secret word is drawn after the line is written, so
from `[play]` on nothing more is passed on and the gateway says the rest once it is checked
(the character prompt puts `[play]` first, so in practice the whole line waits). The gateway owns
how text is said: it holds back unfinished brackets and strips commands before anything is spoken.
"""

from collections.abc import AsyncIterator
from contextlib import aclosing

from mochi_backend.intelligence.character_port import (
    CharacterRequest,
    CharacterStreamError,
    StreamingCharacterModel,
)
from mochi_backend.platform.text_sink import TextSink

QUIET = "[quiet]"
PLAY = "[play]"


class _LineSoFar:
    """Everything written so far, and whether passing it on has to stop."""

    def __init__(self, sink: TextSink) -> None:
        self.text = ""
        self._sink = sink
        self._held = False

    async def follow(self, pieces: AsyncIterator[str]) -> None:
        """Take every piece; pass each on unless Mochi chose silence or a round is starting."""
        async for piece in pieces:
            self.text += piece
            written = self.text.lower()
            self._held = self._held or QUIET in written or PLAY in written
            if not self._held:
                self._sink.put(piece)


async def streamed_line(
    model: StreamingCharacterModel, request: CharacterRequest, sink: TextSink
) -> str | None:
    """The model's whole answer, passing each safe piece to `sink` as it is written.

    None when the stream broke off: the pieces already passed on stay said, the line is not
    remembered. Example: `await streamed_line(model, request, outlet)`.
    """
    line = _LineSoFar(sink)
    try:
        async with aclosing(model.stream_reply(request)) as pieces:
            await line.follow(pieces)
    except CharacterStreamError:
        return None
    return line.text
