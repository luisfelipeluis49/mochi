"""Fake Agora client and token issuer: record calls, fail on demand. No network."""

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStopped,
    AgentStartRequest,
    AgoraError,
)


class FakeAgoraClient:
    """Implements `AgoraAgentClient`. Set `start_error` / `stop_error` to script failures."""

    def __init__(self) -> None:
        self.started: list[AgentStartRequest] = []
        self.stopped: list[str] = []
        self.spoken: list[tuple[str, str]] = []
        self.start_error: AgoraError | None = None
        self.stop_error: AgoraError | AgentAlreadyStopped | None = None
        self.speak_error: AgoraError | None = None

    async def start_agent(self, request: AgentStartRequest) -> str:
        """Record the start (or raise the scripted error); returns "agent-N"."""
        if self.start_error is not None:
            raise self.start_error
        self.started.append(request)
        return f"agent-{len(self.started)}"

    async def stop_agent(self, agent_id: str) -> None:
        """Record the stop (or raise the scripted error)."""
        self.stopped.append(agent_id)
        if self.stop_error is not None:
            raise self.stop_error

    async def speak(self, agent_id: str, text: str) -> None:
        """Record the spoken line (or raise the scripted error)."""
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
