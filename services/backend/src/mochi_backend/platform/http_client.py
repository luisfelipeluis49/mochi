"""HTTP behind a project-owned protocol; httpx is an implementation detail."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import httpx

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


class HttpxClient:
    """HttpClient over httpx. Example: `await HttpxClient().post_json(url, {}, {"a": 1}, 2.0)`."""

    async def post_json(
        self, url: str, headers: Mapping[str, str], payload: JsonValue, timeout_seconds: float
    ) -> HttpResponse:
        """POST JSON, translating httpx errors into `HttpTransportError`."""
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                reply = await client.post(url, headers=dict(headers), json=payload)
        except httpx.HTTPError as error:
            raise HttpTransportError(
                f"POST {url} failed: {error!r}; expected an HTTP reply within {timeout_seconds}s"
            ) from error
        return HttpResponse(status=reply.status_code, body=reply.text)
