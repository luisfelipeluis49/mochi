"""Scripted server-sent-event lines. Example: `FakeLineStreamer(["data: [DONE]"])`."""

from collections.abc import AsyncIterator, Mapping

from mochi_backend.platform.http_client import HttpTransportError, JsonValue
from tests.fakes.fake_http_client import RecordedPost


class FakeLineStreamer:
    """Implements `HttpLineStreamer`. Yields `lines`; an `HttpTransportError` in them is raised."""

    def __init__(self, lines: list[str | HttpTransportError]) -> None:
        self._lines = list(lines)
        self.posts: list[RecordedPost] = []

    async def post_lines(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> AsyncIterator[str]:
        """Record the call, then yield the scripted lines in order."""
        self.posts.append(RecordedPost(url, headers, payload, timeout_seconds))
        for line in self._lines:
            if isinstance(line, HttpTransportError):
                raise line
            yield line
