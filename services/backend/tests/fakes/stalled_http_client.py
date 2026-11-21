"""An HTTP client whose first request stalls. Example: `StalledFirstHttpClient(reply)`."""

import asyncio
from collections.abc import Mapping

from mochi_backend.platform.http_client import HttpResponse, JsonValue


class StalledFirstHttpClient:
    """Implements `HttpClient`. The first POST waits for `release`; every later one answers.

    `stalled_cancelled` tells whether the stalled request was cancelled by its caller.
    """

    def __init__(self, reply: HttpResponse) -> None:
        self._reply = reply
        self.release = asyncio.Event()
        self.calls = 0
        self.stalled_cancelled = False

    async def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> HttpResponse:
        """The first call waits for `release`; the rest return the scripted reply at once."""
        self.calls += 1
        if self.calls > 1:
            return self._reply
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.stalled_cancelled = True
            raise
        return self._reply
