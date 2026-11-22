"""`MOCHI_AGORA_MODE=fake`: run the whole server locally without Agora."""

from mochi_backend.gateway.agora.client_port import AgentStartRequest
from mochi_backend.platform.json_logging import EventLogger


class LocalMockAgoraClient:
    """Pretends to start, stop and speak. Logs instead of calling Agora."""

    def __init__(self, logger: EventLogger) -> None:
        self._logger = logger
        self._started = 0

    async def start_agent(self, request: AgentStartRequest) -> str:
        """Return a fake agent id. Example: "mock-agent-1"."""
        self._started += 1
        self._logger.log("mock_agora_start", {"channel": request.channel, "uid": request.agent_uid})
        return f"mock-agent-{self._started}"

    async def stop_agent(self, agent_id: str) -> None:
        """Log the stop."""
        self._logger.log("mock_agora_stop", {"agent_id": agent_id})

    async def speak(self, agent_id: str, text: str) -> None:
        """Log what the agent would say."""
        self._logger.log("mock_agora_speak", {"agent_id": agent_id, "text": text})

    async def interrupt(self, agent_id: str) -> None:
        """Log that the agent would stop talking."""
        self._logger.log("mock_agora_interrupt", {"agent_id": agent_id})


class LocalMockTokenIssuer:
    """Returns an obviously fake token."""

    def issue(self, channel: str, uid: int, ttl_seconds: int) -> str:
        """Example: "mock-token-mochi-demo-1001"."""
        return f"mock-token-{channel}-{uid}"
