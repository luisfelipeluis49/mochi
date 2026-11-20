"""Fake Agora client and token issuer: record calls, fail on demand. No network."""

import asyncio

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStoppedError,
    AgentStartRequest,
    AgoraError,
    AgoraRejectedError,
)


class FakeAgoraClient:
    """Implements `AgoraAgentClient`. Set `start_error` / `stop_error` to script failures."""

    def __init__(self) -> None:
        self.started: list[AgentStartRequest] = []
        self.stopped: list[str] = []
        self.spoken: list[tuple[str, str]] = []
        self.start_error: AgoraError | None = None
        self.refused_ears: set[str] = set()  # speech-to-text vendors Agora "does not accept"
        self.attempts: list[AgentStartRequest] = []  # every start, refused ones included
        self.stop_error: AgoraError | AgentAlreadyStoppedError | None = None
        self.speak_error: AgoraError | None = None
        self.start_gate: asyncio.Event | None = None  # when set, start_agent waits for it
        self.stop_gate: asyncio.Event | None = None  # when set, stop_agent waits for it
        self.speak_gate: asyncio.Event | None = None  # when set, speak waits for it
        self.start_entered = asyncio.Event()
        self.stop_entered = asyncio.Event()

    async def start_agent(self, request: AgentStartRequest) -> str:
        """Record the start (or raise the scripted error); returns "agent-N"."""
        self.attempts.append(request)
        if self.start_error is not None:
            raise self.start_error
        if request.tuning.asr_vendor in self.refused_ears:
            raise AgoraRejectedError(f"vendor {request.tuning.asr_vendor!r} is not available")
        self.started.append(request)
        agent_id = f"agent-{len(self.started)}"
        self.start_entered.set()
        if self.start_gate is not None:
            await self.start_gate.wait()
        return agent_id

    async def stop_agent(self, agent_id: str) -> None:
        """Record the stop (or raise the scripted error)."""
        self.stopped.append(agent_id)
        self.stop_entered.set()
        if self.stop_gate is not None:
            await self.stop_gate.wait()
        if self.stop_error is not None:
            raise self.stop_error

    async def speak(self, agent_id: str, text: str) -> None:
        """Record the spoken line (or raise the scripted error)."""
        if self.speak_gate is not None:
            await self.speak_gate.wait()
        if self.speak_error is not None:
            raise self.speak_error
        self.spoken.append((agent_id, text))


class FakeTokenIssuer:
    """Implements `RtcTokenIssuer`; counts how many tokens were issued."""

    def __init__(self) -> None:
        self.issued: list[tuple[str, int, int]] = []

    def issue(self, channel: str, uid: int, ttl_seconds: int) -> str:
        """Example: "token-mochi-demo-1001-1"."""
        self.issued.append((channel, uid, ttl_seconds))
        return f"token-{channel}-{uid}-{len(self.issued)}"
