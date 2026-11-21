"""Reading a streamed chat completion (`stream: true`): content deltas, then usage, then [DONE].

OpenAI-compatible servers send `data: <chunk>` lines; with `stream_options.include_usage` the
last chunk before `data: [DONE]` has no choices and carries `usage` (OpenAI API reference,
"chat completion chunk"). A stream that ends without [DONE] was cut off.
"""

from pydantic import BaseModel

from mochi_backend.intelligence.model_usage import ModelUsage

DONE = "[DONE]"


class _Delta(BaseModel):
    content: str | None = None


class _StreamChoice(BaseModel):
    delta: _Delta = _Delta()


class StreamChunk(BaseModel):
    """One `data:` line of a streamed completion."""

    choices: list[_StreamChoice] = []
    usage: ModelUsage | None = None

    @property
    def text(self) -> str:
        """The content this chunk adds ("" for role, usage and stop chunks)."""
        return "".join(choice.delta.content or "" for choice in self.choices)


def chunk_of(line: str) -> StreamChunk | None:
    """The chunk on one SSE line; None for blank lines, comments and the [DONE] line.

    Example: `chunk_of('data: {"choices": [{"delta": {"content": "Hi"}}]}').text` is "Hi".
    Raises `pydantic.ValidationError` for a `data:` line that is not a chunk.
    """
    payload = line.removeprefix("data:").strip() if line.startswith("data:") else ""
    if not payload or payload == DONE:
        return None
    return StreamChunk.model_validate_json(payload)


def is_done(line: str) -> bool:
    """True for the `data: [DONE]` line that ends a complete stream."""
    return line.startswith("data:") and line.removeprefix("data:").strip() == DONE
