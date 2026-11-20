"""The only module that calls the Agora Conversational AI REST API (see VERIFIED.md)."""

import base64

from pydantic import BaseModel, ValidationError

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStoppedError,
    AgentStartRequest,
    AgoraError,
    SpeechTuning,
)
from mochi_backend.platform.http_client import (
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_SERVER_ERROR,
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
        if reply.status != HTTP_OK:
            raise AgoraError(_describe(url, reply, "200 with a JSON body containing agent_id"))
        try:
            return _JoinReply.model_validate_json(reply.body).agent_id
        except ValidationError as error:
            raise AgoraError(_describe(url, reply, "a JSON body containing agent_id")) from error

    async def stop_agent(self, agent_id: str) -> None:
        """POST /agents/{id}/leave. A 404 means the agent is already gone."""
        url = f"{self._root}/agents/{agent_id}/leave"
        reply = await self._post(url, None, attempts=2)  # leaving twice is harmless
        if reply.status == HTTP_NOT_FOUND:
            raise AgentAlreadyStoppedError(f"agent {agent_id!r} not found at {url}")
        if reply.status != HTTP_OK:
            raise AgoraError(_describe(url, reply, "200 with an empty body"))

    async def speak(self, agent_id: str, text: str) -> None:
        """POST /agents/{id}/speak (max 512 bytes of text; interrupts whatever is playing)."""
        url = f"{self._root}/agents/{agent_id}/speak"
        clipped = text.encode()[:SPEAK_MAX_BYTES].decode(errors="ignore")
        reply = await self._post(
            url, {"text": clipped, "priority": "INTERRUPT", "interruptable": True}
        )
        if reply.status != HTTP_OK:
            raise AgoraError(_describe(url, reply, "200"))

    async def _post(self, url: str, payload: JsonValue, attempts: int = 1) -> HttpResponse:
        """POST once, or up to `attempts` times for calls that are safe to repeat (/leave only)."""
        last_error: HttpTransportError | None = None
        reply: HttpResponse | None = None
        for _attempt in range(attempts):
            try:
                reply = await self._http.post_json(url, self._headers, payload, TIMEOUT_SECONDS)
            except HttpTransportError as error:
                last_error, reply = error, None
                continue
            if reply.status < HTTP_SERVER_ERROR:
                return reply
        if reply is not None:
            return reply  # the last 5xx; the caller reports it with its body
        suffix = "s" if attempts > 1 else ""
        raise AgoraError(f"POST {url} failed after {attempts} attempt{suffix}: {last_error}")


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


def _vendor_block(
    vendor: str, mode: str, params: dict[str, JsonValue], extra: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    block: dict[str, JsonValue] = {"vendor": vendor, **extra}
    if mode:
        block["credential_mode"] = mode
    if params:
        block["params"] = params
    return block


def _asr_block(tuning: SpeechTuning) -> dict[str, JsonValue]:
    extra: dict[str, JsonValue] = {"language": tuning.asr_language}
    if tuning.asr_keywords:
        extra["keywords"] = list(tuning.asr_keywords)
    return _vendor_block(tuning.asr_vendor, tuning.asr_credential_mode, tuning.asr_params, extra)


def _speech_blocks(tuning: SpeechTuning) -> dict[str, JsonValue]:
    """Several languages ("en-US,pt-PT") are one comma-separated string, also in turn detection."""
    tts = _vendor_block(tuning.tts_vendor, tuning.tts_credential_mode, tuning.tts_params, {})
    vad: dict[str, JsonValue] = {"silence_duration_ms": tuning.end_of_speech_silence_ms}
    turns: dict[str, JsonValue] = {"config": {"end_of_speech": {"mode": "vad", "vad_config": vad}}}
    if "," in tuning.asr_language:
        turns["language"] = tuning.asr_language
    return {"asr": _asr_block(tuning), "tts": tts, "turn_detection": turns}


def join_body(request: AgentStartRequest, name: str) -> JsonValue:
    """The /join request body (field names verified in VERIFIED.md)."""
    properties: dict[str, JsonValue] = {
        "channel": request.channel,
        "token": request.token,
        "agent_rtc_uid": str(request.agent_uid),
        "remote_rtc_uids": [str(request.remote_uid)],
        "llm": _llm_block(request),
        "idle_timeout": request.idle_timeout_seconds,  # agent leaves this long after the Pi does
        "parameters": {"silence_config": {"timeout_ms": 0}},
        **_speech_blocks(request.tuning),
    }
    return {"name": name, "properties": properties}
