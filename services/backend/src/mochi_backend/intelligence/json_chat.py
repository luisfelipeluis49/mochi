"""One JSON answer from an OpenAI-compatible chat-completions API. Never raises.

Shared by the models that are asked for strict JSON outside the hint judge: the explainer (D-53)
and the speech coach (D-54). The caller writes the messages and parses the answer.
"""

import time
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.model_usage import ModelUsage, log_usage
from mochi_backend.intelligence.warm_start import open_connections
from mochi_backend.platform.http_client import (
    HTTP_OK,
    HttpClient,
    HttpGetter,
    HttpTransportError,
    JsonValue,
)
from mochi_backend.platform.json_logging import EventLogger


@dataclass(frozen=True)
class JsonChatConfig:
    """Which model to ask and how. `reasoning_effort`: "" for models without the setting."""

    base_url: str
    model_name: str
    api_key: str
    timeout_seconds: float
    reasoning_effort: str = ""


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatReply(BaseModel):
    choices: list[_Choice]
    usage: ModelUsage | None = None


class JsonChat:
    """Example: `await JsonChat(http, config, "explain", logger).ask(messages)` -> JSON text."""

    def __init__(
        self, http: HttpClient, config: JsonChatConfig, kind: str, logger: EventLogger | None = None
    ) -> None:
        self._http = http
        self._config = config
        self._kind = kind  # what the call is for, in the usage and failure log lines
        self._logger = logger
        self._getter: HttpGetter | None = None

    def warming(self, getter: HttpGetter) -> "JsonChat":
        """Let `warm_up` open connections through `getter` (the client that also posts)."""
        self._getter = getter
        return self

    async def warm_up(self) -> None:
        """Open the connections a sentence will use (see `warm_start`). Never raises."""
        if self._getter is None:
            return
        config = self._config
        await open_connections(self._getter, config.base_url, config.model_name, config.api_key)

    def _payload(self, messages: list[JsonValue]) -> JsonValue:
        effort = self._config.reasoning_effort
        sampling: dict[str, JsonValue] = (
            {"reasoning_effort": effort} if effort else {"temperature": 0}
        )
        return {
            "model": self._config.model_name,
            **sampling,
            "response_format": {"type": "json_object"},
            "messages": messages,
        }

    def _failed(self, why: str) -> None:
        """Log what failed, never the text that was sent or the key."""
        if self._logger is not None:
            what = {"model": self._config.model_name, "kind": self._kind, "why": why}
            self._logger.log("json_model_failed", what)

    async def ask(self, messages: list[JsonValue]) -> str | None:
        """The model's answer as text; None on a transport error, a non-200 or a broken reply."""
        url = f"{self._config.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        started = time.monotonic()
        try:
            reply = await self._http.post_json(
                url, headers, self._payload(messages), self._config.timeout_seconds
            )
            if reply.status != HTTP_OK:
                self._failed(f"HTTP {reply.status}")
                return None
            answer = _ChatReply.model_validate_json(reply.body)
            log_usage(self._logger, self._config.model_name, self._kind, answer.usage, started)
            return answer.choices[0].message.content
        except (HttpTransportError, ValidationError, IndexError) as error:
            self._failed(type(error).__name__)  # the class only: a message may quote a sentence
            return None
