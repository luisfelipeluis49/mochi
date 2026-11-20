"""Ports for everything Agora. Only `rest_client.py` and `token_issuer.py` implement them."""

from dataclasses import dataclass, field
from typing import Protocol

from mochi_backend.platform.http_client import JsonValue

VendorParams = dict[str, JsonValue]


class AgoraError(Exception):
    """An Agora call failed. The message names the endpoint, status and expected shape."""


class AgoraRejectedError(AgoraError):
    """Agora refused the request itself (a 4xx): the same request would be refused again."""


class AgentAlreadyStoppedError(AgoraError):
    """The agent was already gone when we tried to stop it (tolerated)."""


@dataclass(frozen=True)
class SpeechTuning:
    """ASR/TTS/turn-detection settings passed through from the environment."""

    asr_vendor: str = "ares"
    asr_language: str = "en-US"  # several for ARES: one comma-separated string, "en-US,pt-PT"
    asr_keywords: tuple[str, ...] = ()  # words the recogniser should expect (ARES only)
    asr_params: VendorParams = field(default_factory=dict)
    asr_credential_mode: str = ""
    tts_vendor: str = "minimax"
    tts_params: VendorParams = field(default_factory=dict)
    tts_credential_mode: str = ""
    end_of_speech_silence_ms: int = 900


@dataclass(frozen=True)
class AgentStartRequest:
    """Everything needed to start the Conversational AI agent for one session."""

    channel: str
    agent_uid: int
    remote_uid: int
    token: str
    llm_url: str
    llm_key: str
    tuning: SpeechTuning
    idle_timeout_seconds: int = 60
    greeting: str = ""  # said once when the device joins; empty = Mochi starts silent


class AgoraAgentClient(Protocol):
    """Start, stop and speak through the Conversational AI Engine."""

    async def start_agent(self, request: AgentStartRequest) -> str:
        """Start an agent; returns its agent id."""
        ...

    async def stop_agent(self, agent_id: str) -> None:
        """Stop an agent; raises `AgentAlreadyStoppedError` when it is already gone."""
        ...

    async def speak(self, agent_id: str, text: str) -> None:
        """Make a running agent say `text` without a user turn."""
        ...


class RtcTokenIssuer(Protocol):
    """Builds RTC tokens for the Pi bridge and the agent."""

    def issue(self, channel: str, uid: int, ttl_seconds: int) -> str:
        """Return a token valid for `ttl_seconds` for `uid` in `channel`."""
        ...
