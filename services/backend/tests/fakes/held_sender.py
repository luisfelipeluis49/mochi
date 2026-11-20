"""A client that blocks its first message, to freeze the hub mid-publish in a test."""

import asyncio


class HeldSender:
    """Implements `Sender`: the first message waits for `release`, then all are recorded."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.entered = asyncio.Event()
        self.texts: list[str] = []
        self.sequences: list[int] = []
        self._first = True

    async def send_text(self, text: str) -> None:
        """Hold the first message until released; record every message in arrival order."""
        if self._first:
            self._first = False
            self.entered.set()
            await self.release.wait()
        after_key = text.split('"sequence":')[1]
        self.sequences.append(int(after_key.split(",")[0].strip("}")))
        self.texts.append(text)
