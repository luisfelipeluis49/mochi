"""A scripted HTTP GET client (stands in for Agora's Turns API). No network."""

from collections.abc import Mapping

from mochi_backend.platform.http_client import HttpResponse


class FakeHttpGetter:
    """Implements `HttpGetter`. Answers by the URL's ending; any other URL gets a 404."""

    def __init__(self, replies: Mapping[str, HttpResponse]) -> None:
        self._replies = dict(replies)
        self.urls: list[str] = []
        self.headers: list[Mapping[str, str]] = []

    async def get(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        """Record the call; reply with the first scripted response whose key ends the URL."""
        self.urls.append(url)
        self.headers.append(headers)
        found = [reply for ending, reply in self._replies.items() if url.endswith(ending)]
        return found[0] if found else HttpResponse(404, '{"reason":"TaskNotFound"}')
