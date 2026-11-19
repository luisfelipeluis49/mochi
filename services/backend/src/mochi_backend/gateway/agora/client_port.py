"""Ports for everything Agora. Only `rest_client.py` and `token_issuer.py` implement them."""

from dataclasses import dataclass, field
from typing import Protocol

VendorParams = dict[str, str | int | float | bool]


class AgoraError(Exception):
    """An Agora call failed. The message names the endpoint, status and expected shape."""


class AgentAlreadyStoppedError(AgoraError):
    """The agent was already gone when we tried to stop it (tolerated)."""


@dataclass(frozen=True)
class SpeechTuning:
    """ASR/TTS/turn-detection settings passed through from the environment."""

    asr_vendor: str = "microsoft"
    asr_language: str = "en-US"
    asr_params: VendorParams = field(default_factory=dict)
    tts_vendor: str = "microsoft"
    tts_params: VendorParams = field(default_factory=dict)
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
