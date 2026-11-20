"""`POST /agora/llm/demo/chat/completions`: the turn endpoint Agora's cloud calls."""

import hmac
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from mochi_backend.gateway.openai_sse import completion_json, sse_events
from mochi_backend.gateway.routes.dependencies import ContainerDep

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


@router.post("/agora/llm/demo/chat/completions", response_model=None)
async def chat_completions(
    body: ChatCompletionRequest,
    container: ContainerDep,
    x_mochi_key: Annotated[str | None, Header()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> StreamingResponse | JSONResponse:
    """Reject without the shared key, run the turn, reply with text or silence."""
    expected = container.settings.mochi_turn_key.encode()
    if not hmac.compare_digest(presented_key(x_mochi_key, authorization).encode(), expected):
        raise HTTPException(status_code=401, detail=f"missing or wrong {KEY_HEADER} header")
    outcome = await container.pipeline.handle_turn(last_user_text(body.messages))
    created = int(container.core.clock.now().timestamp())
    if not body.stream:
        return JSONResponse(completion_json(outcome.reply, created))
    return StreamingResponse(_stream(outcome.reply, created), media_type="text/event-stream")


def _stream(reply: str, created: int) -> Iterator[str]:
    yield from sse_events(reply, created)
