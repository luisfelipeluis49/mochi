"""HTTP behind a project-owned protocol; httpx is an implementation detail."""

from collections.abc import Mapping
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


class HttpTransportError(Exception):
    """Connection failure or timeout. The message names the URL and the cause."""


KEEP_ALIVE_SECONDS = 30.0  # sentences in a conversation come a few seconds apart


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
