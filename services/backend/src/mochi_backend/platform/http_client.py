"""HTTP behind a project-owned protocol; httpx is an implementation detail."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Protocol

import httpx

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True)
class HttpResponse:
    """Status and raw body of an HTTP reply."""

    status: int
    body: str


class HttpClient(Protocol):
    """Posts JSON and returns the raw reply. Raises `HttpTransportError` on network failure."""

    async def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> HttpResponse:
        """POST `payload` as JSON to `url`."""
        ...


class HttpGetter(Protocol):
    """Fetches a URL and returns the raw reply. Raises `HttpTransportError` on network failure."""

    async def get(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        """GET `url`."""
        ...


class HttpLineStreamer(Protocol):
    """Posts JSON and yields the reply line by line as it arrives (server-sent events).

    Raises `HttpTransportError` on network failure, a non-200 reply, or a stalled stream.
    """

    def post_lines(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> AsyncIterator[str]:
        """POST `payload` as JSON to `url`; each yielded item is one line of the reply."""
        ...


class HttpTransportError(Exception):
    """Connection failure or timeout. The message names the URL and the cause."""


# Sentences in a conversation come a few seconds apart, but a slide being read, a hint on the
# screen or a lull are longer than 30 s, and the sentence after them paid for a new handshake
# (0.15-0.5 s).
# Measured against the model API: a connection idle for 120 s was still reused (DECISIONS D-42);
# 90 leaves a margin for a network that forgets an idle connection sooner.
KEEP_ALIVE_SECONDS = 90.0


class HttpxClient:
    """HttpClient over httpx. Example: `await HttpxClient().post_json(url, {}, {"a": 1}, 2.0)`.

    Each instance keeps its connections open for a while, so the next call to the same host
    (the model, on every sentence) does not pay for a new TLS handshake.
    """

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _open(self) -> httpx.AsyncClient:
        if self._client is None:
            limits = httpx.Limits(keepalive_expiry=KEEP_ALIVE_SECONDS)
            self._client = httpx.AsyncClient(limits=limits)
        return self._client

    async def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> HttpResponse:
        """POST JSON, translating httpx errors into `HttpTransportError`."""
        try:
            reply = await self._open().post(
                url, headers=dict(headers), json=payload, timeout=timeout_seconds
            )
        except httpx.HTTPError as error:
            raise HttpTransportError(
                f"POST {url} failed: {error!r}; expected an HTTP reply within {timeout_seconds}s"
            ) from error
        return HttpResponse(status=reply.status_code, body=reply.text)

    async def post_lines(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> AsyncIterator[str]:
        """POST JSON and yield the reply's lines as they arrive.

        `timeout_seconds` bounds each wait (connecting, and every gap between two chunks).
        Example: `async for line in HttpxClient().post_lines(url, {}, {"stream": True}, 6.0)`.
        """
        try:
            async for line in self._lines(url, headers, payload, timeout_seconds):
                yield line
        except httpx.HTTPError as error:
            raise HttpTransportError(
                f"POST {url} stream failed: {error!r}; expected lines within {timeout_seconds}s"
            ) from error

    async def _lines(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> AsyncIterator[str]:
        async with self._open().stream(
            "POST", url, headers=dict(headers), json=payload, timeout=timeout_seconds
        ) as reply:
            _refuse_unless_ok(url, reply.status_code)
            async for line in reply.aiter_lines():
                yield line

    async def get(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        """GET, translating httpx errors into `HttpTransportError`."""
        try:
            reply = await self._open().get(url, headers=dict(headers), timeout=timeout_seconds)
        except httpx.HTTPError as error:
            raise HttpTransportError(
                f"GET {url} failed: {error!r}; expected an HTTP reply within {timeout_seconds}s"
            ) from error
        return HttpResponse(status=reply.status_code, body=reply.text)


def _refuse_unless_ok(url: str, status: int) -> None:
    if status != HTTP_OK:
        raise HttpTransportError(f"POST {url} answered HTTP {status}; expected 200 and a stream")
