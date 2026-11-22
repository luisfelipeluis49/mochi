"""Opening the connection to a model before the first sentence needs it (DECISIONS D-42).

Measured: the first call on a new connection takes 0.15 to 0.5 s longer than the next ones, and
on the deployed backend the first sentence of a session took 1.6 s instead of 0.8 s (the second,
hedged request had to open a connection of its own). A session start is known some seconds
before anyone has finished a sentence, so the handshakes are done then.
"""

import asyncio
from typing import Protocol, runtime_checkable

from mochi_backend.platform.http_client import HttpGetter

# The first request, and the second one `hedged.first_answer` sends when the first is slow.
WARM_CONNECTIONS = 2
WARM_UP_SECONDS = 3.0


@runtime_checkable
class WarmsUp(Protocol):
    """A model adapter that can open its connections ahead of use. Never raises."""

    async def warm_up(self) -> None:
        """Open the connections; return when they are open or cannot be."""
        ...


async def open_connections(getter: HttpGetter, base_url: str, model_name: str, key: str) -> None:
    """Ask the API about the model, twice at once: no tokens, and two connections left open.

    Failures are ignored: the sentence that follows opens its own connection, as before.
    Example: `await open_connections(http, "https://api.openai.com/v1", "gpt-x", key)`.
    """
    url = f"{base_url.rstrip('/')}/models/{model_name}"
    headers = {"Authorization": f"Bearer {key}"}
    asks = [getter.get(url, headers, WARM_UP_SECONDS) for _ in range(WARM_CONNECTIONS)]
    await asyncio.gather(*asks, return_exceptions=True)
