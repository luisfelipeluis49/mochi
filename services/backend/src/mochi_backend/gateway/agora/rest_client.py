"""The only module that calls the Agora Conversational AI REST API (see VERIFIED.md)."""

import base64

from pydantic import BaseModel, ValidationError

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStopped,
    AgentStartRequest,
    AgoraError,
    SpeechTuning,
)
from mochi_backend.platform.http_client import (
    HttpClient,
    HttpResponse,
    HttpTransportError,
    JsonValue,
)
from mochi_backend.platform.ids import IdGenerator

BASE_URL = "https://api.agora.io/api/conversational-ai-agent/v2/projects"
KEY_HEADER = "X-Mochi-Key"
TIMEOUT_SECONDS = 10.0
SPEAK_MAX_BYTES = 512  # documented limit of the speak endpoint


class _JoinReply(BaseModel):
    agent_id: str


class AgoraRestClient:
    """Implements `AgoraAgentClient`. One retry on a 5xx or a connection error."""

    def __init__(
        self, http: HttpClient, app_id: str, rest_key: str, rest_secret: str, ids: IdGenerator
    ) -> None:
        self._http = http
        self._root = f"{BASE_URL}/{app_id}"
        self._ids = ids
        basic = base64.b64encode(f"{rest_key}:{rest_secret}".encode()).decode()
        self._headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/json"}

    async def start_agent(self, request: AgentStartRequest) -> str:
        """POST /join; returns `agent_id`. Greeting and failure message are omitted (= off)."""
        url = f"{self._root}/join"
        reply = await self._post(url, join_body(request, self._ids.new("mochi")))
        if reply.status != 200:  # noqa: PLR2004
            raise AgoraError(_describe(url, reply, "200 with a JSON body containing agent_id"))
        try:
            return _JoinReply.model_validate_json(reply.body).agent_id
        except ValidationError as error:
            raise AgoraError(_describe(url, reply, "a JSON body containing agent_id")) from error

    async def stop_agent(self, agent_id: str) -> None:
        """POST /agents/{id}/leave. A 404 means the agent is already gone."""
        url = f"{self._root}/agents/{agent_id}/leave"
        reply = await self._post(url, None)
        if reply.status == 404:  # noqa: PLR2004
            raise AgentAlreadyStopped(f"agent {agent_id!r} not found at {url}")
        if reply.status != 200:  # noqa: PLR2004
            raise AgoraError(_describe(url, reply, "200 with an empty body"))

    async def speak(self, agent_id: str, text: str) -> None:
        """POST /agents/{id}/speak (max 512 bytes of text; interrupts whatever is playing)."""
        url = f"{self._root}/agents/{agent_id}/speak"
        clipped = text.encode()[:SPEAK_MAX_BYTES].decode(errors="ignore")
        reply = await self._post(
            url, {"text": clipped, "priority": "INTERRUPT", "interruptable": True}
        )
        if reply.status != 200:  # noqa: PLR2004
            raise AgoraError(_describe(url, reply, "200"))

    async def _post(self, url: str, payload: JsonValue) -> HttpResponse:
        last_error: HttpTransportError | None = None
        for _attempt in range(2):
            try:
                reply = await self._http.post_json(url, self._headers, payload, TIMEOUT_SECONDS)
            except HttpTransportError as error:
                last_error = error
                continue
            if reply.status < 500:  # noqa: PLR2004
                return reply
            last_error = None
        if last_error is not None:
            raise AgoraError(f"POST {url} failed twice: {last_error}")
        return reply


def _describe(url: str, reply: HttpResponse, expected: str) -> str:
    return f"POST {url} returned {reply.status}; expected {expected}; body: {reply.body[:200]!r}"


def _llm_block(request: AgentStartRequest) -> JsonValue:
    return {
        "url": request.llm_url,
        "api_key": request.llm_key,
        "headers": {KEY_HEADER: request.llm_key},
        "style": "openai",
        "max_history": 8,
    }


def _speech_blocks(tuning: SpeechTuning) -> dict[str, JsonValue]:
    asr: dict[str, JsonValue] = {
        "vendor": tuning.asr_vendor,
        "language": tuning.asr_language,
        "params": dict(tuning.asr_params),
    }
    tts: dict[str, JsonValue] = {"vendor": tuning.tts_vendor, "params": dict(tuning.tts_params)}
    vad: dict[str, JsonValue] = {"silence_duration_ms": tuning.end_of_speech_silence_ms}
    turns: dict[str, JsonValue] = {"config": {"end_of_speech": {"mode": "vad", "vad_config": vad}}}
    return {"asr": asr, "tts": tts, "turn_detection": turns}


def join_body(request: AgentStartRequest, name: str) -> JsonValue:
    """The /join request body (field names verified in VERIFIED.md)."""
    properties: dict[str, JsonValue] = {
        "channel": request.channel,
        "token": request.token,
        "agent_rtc_uid": str(request.agent_uid),
        "remote_rtc_uids": [str(request.remote_uid)],
        "llm": _llm_block(request),
        "parameters": {"silence_config": {"timeout_ms": 0}},
        **_speech_blocks(request.tuning),
    }
    return {"name": name, "properties": properties}
