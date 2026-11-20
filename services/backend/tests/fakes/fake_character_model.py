"""A scripted Mochi. Example: `FakeCharacterModel("[mood happy] Oi!")` always says that."""

import asyncio

from mochi_backend.intelligence.character_port import CharacterRequest


class FakeCharacterModel:
    """Implements `CharacterModel`. Answers from `lines` in order (the last one repeats)."""

    def __init__(self, *lines: str | None, delay_seconds: float = 0.0) -> None:
        self._lines = list(lines)
        self._delay = delay_seconds
        self.requests: list[CharacterRequest] = []

    async def reply(self, request: CharacterRequest) -> str | None:
        """Record the request, then answer as scripted."""
        self.requests.append(request)
        if self._delay:
            await asyncio.sleep(self._delay)
        if not self._lines:
            return None
        return self._lines.pop(0) if len(self._lines) > 1 else self._lines[0]
