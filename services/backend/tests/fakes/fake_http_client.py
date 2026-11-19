"""A scripted HTTP client that records every call. No network."""

from collections.abc import Mapping
from dataclasses import dataclass

from mochi_backend.platform.http_client import HttpResponse, HttpTransportError, JsonValue


@dataclass(frozen=True)
class RecordedPost:
    """One POST the code under test made."""

    url: str
    headers: Mapping[str, str]
    payload: JsonValue
    timeout_seconds: float


class FakeHttpClient:
    """Implements `HttpClient`. Replies are consumed in order; an Exception is raised."""

    def __init__(self, replies: list[HttpResponse | HttpTransportError]) -> None:
        self._replies = list(replies)
        self.posts: list[RecordedPost] = []

    async def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> HttpResponse:
        """Record the call and return the next scripted reply."""
        self.posts.append(RecordedPost(url, headers, payload, timeout_seconds))
        reply = self._replies.pop(0)
        if isinstance(reply, HttpTransportError):
            raise reply
        return reply
