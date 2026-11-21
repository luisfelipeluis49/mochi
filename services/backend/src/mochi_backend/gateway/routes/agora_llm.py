"""`POST /agora/llm/demo/chat/completions`: the turn endpoint Agora's cloud calls."""

import hmac
import time
from collections.abc import AsyncIterator, Iterator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.openai_sse import (
    closing_lines,
    completion_json,
    content_chunk,
    sse_events,
)
from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_backend.gateway.spoken_release import SpokenOutlet
from mochi_backend.gateway.stale_turns import Gone
from mochi_backend.gateway.turn_pipeline import TurnOutcome
from mochi_backend.platform.json_logging import EventLogger

router = APIRouter()
KEY_HEADER = "x-mochi-key"  # set through llm.headers when the agent is started


class ContentPart(BaseModel):
    """One part of a multi-part message content."""

    type: str = "text"
    text: str | None = None


class ChatMessage(BaseModel):
    """One OpenAI-style message. Unknown fields are ignored."""

    role: str
    content: str | list[ContentPart] | None = None


class ChatCompletionRequest(BaseModel):
    """The slice of Agora's request we use: the messages and whether to stream."""

    messages: list[ChatMessage] = []
    stream: bool = True


def last_user_text(messages: list[ChatMessage]) -> str:
    """Text of the last `user` message. Example: [system, user "hi"] -> "hi"."""
    for message in reversed(messages):
        if message.role == "user":
            return _text_of(message.content)
    return ""


def last_user_position(messages: list[ChatMessage]) -> int:
    """Index of the last `user` message, -1 when there is none. Example: [system, user] -> 1."""
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "user":
            return index
    return -1


def _text_of(content: str | list[ContentPart] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return " ".join(part.text or "" for part in content if part.type == "text").strip()


def presented_key(x_mochi_key: str | None, authorization: str | None) -> str:
    """The shared key from our own header, else from `Authorization: Bearer`."""
    if x_mochi_key:
        return x_mochi_key
    scheme, _, token = (authorization or "").strip().partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def hang_up_signal(request: Request) -> Gone:
    """A wait that returns once the caller closed the connection (ASGI `http.disconnect`).

    The body has been read by then, so the next message the server gives is the disconnect.
    Example: `await hang_up_signal(request)()` returns when Agora hangs up.
    """

    async def hung_up() -> None:
        """Wait for the disconnect message. Example: `await hung_up()`."""
        while (await request.receive())["type"] != "http.disconnect":
            continue

    return hung_up


@router.post("/agora/llm/demo/chat/completions", response_model=None)
async def chat_completions(
    body: ChatCompletionRequest,
    container: ContainerDep,
    request: Request,
    x_mochi_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse | JSONResponse:
    """Reject without the shared key, run the turn, reply with text or silence."""
    arrived = time.monotonic()
    container.core.logger.log(
        "turn_arrived",
        {"arrived_monotonic": round(arrived, 3), "messages": len(body.messages)},
    )
    expected = container.settings.mochi_turn_key.encode()
    if not hmac.compare_digest(presented_key(x_mochi_key, authorization).encode(), expected):
        raise HTTPException(status_code=401, detail=f"missing or wrong {KEY_HEADER} header")
    gone = hang_up_signal(request) if container.settings.mochi_cancel_stale_turns else None
    said, position = last_user_text(body.messages), last_user_position(body.messages)
    outcome = await container.pipeline.handle_heard(said, position, arrived, gone, body.stream)
    return _answer(outcome, body.stream, container, arrived)


def _answer(
    outcome: TurnOutcome, stream: bool, container: AppContainer, arrived: float
) -> StreamingResponse | JSONResponse:
    """The reply in the shape Agora asked for; a streamed turn reads from its outlet (D-37)."""
    created = int(container.core.clock.now().timestamp())
    logger = container.core.logger
    if outcome.spoken is not None:
        spoken = _spoken_stream(outcome.spoken, created, logger, arrived)
        return StreamingResponse(spoken, media_type="text/event-stream")
    if not stream:
        return JSONResponse(completion_json(outcome.reply, created))
    whole = _stream(outcome.reply, created, logger, outcome.segment_id, arrived)
    return StreamingResponse(whole, media_type="text/event-stream")


def _log_first_byte(logger: EventLogger, segment_id: str | None, arrived: float) -> None:
    millis = (time.monotonic() - arrived) * 1000
    logger.log(
        "reply_first_byte",
        {
            "segment_id": segment_id,
            "arrived_monotonic": round(arrived, 3),
            "arrived_to_first_byte_ms": round(millis, 1),
        },
    )


async def _spoken_stream(
    spoken: SpokenOutlet, created: int, logger: EventLogger, arrived: float
) -> AsyncIterator[str]:
    """MOCHI_STREAM_REPLY: one content delta per released piece, then stop and [DONE].

    No empty first chunk: the first chunk carries words (or is the empty reply of a silent turn).
    """
    first = True
    async for piece in spoken.pieces():
        if first:
            _log_first_byte(logger, spoken.segment_id, arrived)
        yield content_chunk(piece, created, first=first)
        first = False
    if first:
        _log_first_byte(logger, spoken.segment_id, arrived)
        yield content_chunk("", created, first=True)
    for line in closing_lines(created):
        yield line


def _stream(
    reply: str,
    created: int,
    logger: EventLogger,
    segment_id: str | None = None,
    arrived: float | None = None,
) -> Iterator[str]:
    first = True
    for chunk in sse_events(reply, created):
        if first and arrived is not None:
            first = False
            _log_first_byte(logger, segment_id, arrived)
        yield chunk
