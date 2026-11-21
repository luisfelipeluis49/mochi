"""What one model call cost: tokens in, tokens out, tokens served from the prompt cache.

OpenAI-compatible replies carry `usage` (`prompt_tokens`, `completion_tokens` and, where the
provider caches prompts, `prompt_tokens_details.cached_tokens`). One `model_usage` line per call
lets the cost of every latency lever be read from the log (DECISIONS D-37). Never the text.
"""

import time

from pydantic import BaseModel

from mochi_backend.platform.json_logging import EventLogger


class _PromptDetails(BaseModel):
    cached_tokens: int | None = None


class ModelUsage(BaseModel):
    """The `usage` object of a chat-completions reply (or of the last chunk of a stream)."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    prompt_tokens_details: _PromptDetails | None = None


def log_usage(
    logger: EventLogger | None, model: str, kind: str, usage: ModelUsage | None, started: float
) -> None:
    """Log `model_usage` for one call that answered; nothing without a logger or a `usage`.

    `kind` is "hint" or "character"; `started` is `time.monotonic()` when the call began.
    Example: `log_usage(logger, "gpt-x", "hint", reply.usage, started)`.
    """
    if logger is None or usage is None:
        return
    details = usage.prompt_tokens_details
    logger.log(
        "model_usage",
        {
            "model": model,
            "kind": kind,
            "prompt_tokens": usage.prompt_tokens or 0,
            "completion_tokens": usage.completion_tokens or 0,
            "cached_tokens": (details.cached_tokens if details else None) or 0,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
        },
    )
