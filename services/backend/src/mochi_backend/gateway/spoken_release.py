"""What of Mochi's streamed line may be said yet (MOCHI_STREAM_REPLY, DECISIONS D-37).

Text is released only as `split_commands` would say it: an unfinished `[...` is held until its
`]`, and every bracket is dropped, so a command never reaches the voice. The first piece waits
for a clause end or a few words (a lone "I" is not worth a chunk); later pieces go as soon as a
word is complete. Everything released is a prefix of the line the commit finally says.
"""

import asyncio
from collections.abc import AsyncIterator, Callable

from mochi_backend.gateway.device_commands import split_commands

CLAUSE_ENDS = ".,?!"
FIRST_PIECE_WORDS = 6


def _complete_part(raw: str) -> str:
    """`raw` up to an unfinished bracket, and without a word that may still be growing."""
    growing = bool(raw) and not raw[-1].isspace()
    words = raw[: max(raw.rfind(" "), raw.rfind("\n")) + 1] if growing else raw
    opened, closed = words.rfind("["), words.rfind("]")
    return words[:opened] if opened > closed else words


class SpokenRelease:
    """Example: `release.feed("Hi there, how")` is "Hi there,"; `release.rest(line)` the tail."""

    def __init__(self) -> None:
        self._raw = ""
        self.said = ""

    def feed(self, piece: str) -> str:
        """Add raw model text; return what may be said now ("" = nothing yet)."""
        self._raw += piece
        spoken, _ = split_commands(_complete_part(self._raw))
        if not spoken.startswith(self.said):
            return ""
        fresh = spoken[len(self.said) :]
        if not self.said and not _worth_a_first_piece(fresh):
            return ""
        self.said = spoken
        return fresh

    def rest(self, reply: str) -> str:
        """What is left to say of the reply the commit settled on ("" when it is not ours)."""
        if not reply.startswith(self.said):
            return ""
        fresh = reply[len(self.said) :]
        self.said = reply
        return fresh


def _worth_a_first_piece(text: str) -> bool:
    return any(mark in text for mark in CLAUSE_ENDS) or len(text.split()) >= FIRST_PIECE_WORDS


class SpokenOutlet:
    """The `TextSink` the pipeline hands intelligence, and what the route streams from.

    `may_speak` is asked before every piece: a Stop, a Reset or a round starting ends the
    stream. Example: `outlet.put("Hi, ")`, `outlet.finish(reply)`, `async for p in outlet.pieces()`.
    """

    def __init__(self, may_speak: Callable[[], bool]) -> None:
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._release = SpokenRelease()
        self._may_speak = may_speak
        self._silenced = False
        self.segment_id: str | None = None

    def put(self, text: str) -> None:
        """Take raw model text; queue what may be said of it now."""
        self._silenced = self._silenced or not self._may_speak()
        fresh = "" if self._silenced else self._release.feed(text)
        if fresh:
            self._queue.put_nowait(fresh)

    def spoken(self) -> bool:
        """True once any of the reply has been queued to be said."""
        return bool(self._release.said)

    def finish(self, reply: str) -> None:
        """The commit's final reply: queue whatever of it was not said yet, then end."""
        fresh = self._release.rest(reply)
        if fresh:
            self._queue.put_nowait(fresh)
        self.close()

    def close(self) -> None:
        """End the stream (idempotent enough: a second end marker is never read)."""
        self._queue.put_nowait(None)

    async def pieces(self) -> AsyncIterator[str]:
        """Every piece to say, in order, until the end."""
        while (piece := await self._queue.get()) is not None:
            yield piece
