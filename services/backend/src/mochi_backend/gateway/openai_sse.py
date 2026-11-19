"""OpenAI-style chat-completion replies for Agora's custom-LLM mode.

Agora expects `data: <json>` chunks ending with `data: [DONE]` (see agora/VERIFIED.md).
An empty reply is a valid stream whose only chunk has empty content.
"""

import json
from collections.abc import Iterator

from pydantic import BaseModel

DONE_LINE = "data: [DONE]\n\n"
COMPLETION_ID = "chatcmpl-mochi"


class _Delta(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    delta: _Delta = _Delta()
    finish_reason: str | None = None


class ParsedChunk(BaseModel):
    """What `parse_stream` returns for one `data:` line."""

    choices: list[_Choice] = []


def _chunk(content: str, finish_reason: str | None) -> str:
    delta = {"role": "assistant", "content": content}
    body = {
        "id": COMPLETION_ID,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"


def sse_events(text: str) -> Iterator[str]:
    """The SSE lines for a reply: one content chunk, a stop chunk, then [DONE].

    Example: `"".join(sse_events(""))` is a valid empty reply.
    """
    if text:
        yield _chunk(text, None)
    yield _chunk("", "stop")
    yield DONE_LINE


def completion_json(text: str) -> dict[str, object]:
    """Non-streaming completion object, for `stream: false` callers."""
    message = {"role": "assistant", "content": text}
    return {
        "id": COMPLETION_ID,
        "object": "chat.completion",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
    }


def _payload_of(line: str) -> str:
    return line.removeprefix("data: ").strip() if line.startswith("data: ") else ""


def parse_stream(raw: str) -> tuple[str, bool]:
    """Join the content of every chunk and report whether the stream ended with [DONE]."""
    payloads = [_payload_of(line) for line in raw.splitlines()]
    chunks = [ParsedChunk.model_validate_json(p) for p in payloads if p and p != "[DONE]"]
    pieces = [c.delta.content or "" for chunk in chunks for c in chunk.choices]
    return "".join(pieces), "[DONE]" in payloads
