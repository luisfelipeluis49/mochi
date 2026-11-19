"""HintModel over any OpenAI-compatible chat-completions API. Never raises; returns None instead."""

import json

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.platform.http_client import HTTP_OK, HttpClient, HttpTransportError, JsonValue

SYSTEM_PROMPT = (
    "You help two people practice a language by talking to each other. Judge ONE sentence in "
    "context. Decide whether the speaker is stuck on a word or short expression. Reasons: "
    "code_switch, says_unknown, asks_partner, asks_mochi, trails_off, talks_around, restarts, "
    "look_alike, not_understood. Say IGNORE for: thinking aloud, self-corrections, deliberate "
    "switches (names, dishes, places), small grammar slips, personal or serious talk. Reply with "
    'strict JSON only: {"decision": "IGNORE"|"SHOW_HINT", "reason": <reason or null>, '
    '"expression": <word in the focus language or null>, "meaning": <word in the other '
    'language or null>, "example": <short example sentence or null>}.'
)


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatReply(BaseModel):
    choices: list[_Choice]


class OpenAiHintModel:
    """Example: `OpenAiHintModel(http, base_url, "model", key, 2.0)`; see `suggest`."""

    def __init__(
        self, http: HttpClient, base_url: str, model_name: str, api_key: str, timeout_seconds: float
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model_name = model_name
        self._api_key = api_key
        self._timeout = timeout_seconds

    def _payload(self, request: ModelRequest) -> JsonValue:
        context = {
            "focus": request.focus.value,
            "recent": request.recent_texts,
            "sentence": request.text,
        }
        return {
            "model": self._model_name,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        }

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """Ask the model; None on transport error, non-200, or output that is not strict JSON."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            reply = await self._http.post_json(
                self._url, headers, self._payload(request), self._timeout
            )
            if reply.status != HTTP_OK:
                return None
            content = _ChatReply.model_validate_json(reply.body).choices[0].message.content
            return ModelSuggestion.model_validate_json(content)
        except (HttpTransportError, ValidationError, IndexError):
            return None
