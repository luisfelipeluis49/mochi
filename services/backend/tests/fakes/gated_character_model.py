"""A character model that never answers. Example: `GatedCharacterModel()` blocks until `open()`."""

import asyncio

from mochi_backend.intelligence.character_port import CharacterRequest


class GatedCharacterModel:
    """Implements `CharacterModel`. `reply` waits for `open()`, so a test proves a hint does not."""

    def __init__(self, line: str | None = None) -> None:
        self._gate = asyncio.Event()
        self._line = line
        self.requests: list[CharacterRequest] = []

    def open(self) -> None:
        """Let every waiting and later `reply` answer."""
        self._gate.set()

    async def reply(self, request: CharacterRequest) -> str | None:
        """Record the request, wait for the gate, then answer."""
        self.requests.append(request)
        await self._gate.wait()
        return self._line
