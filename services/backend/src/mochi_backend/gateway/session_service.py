"""Start and stop the session (and with it the Agora agent)."""

from dataclasses import dataclass
from datetime import timedelta

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStopped,
    AgentStartRequest,
    AgoraAgentClient,
    AgoraError,
    RtcTokenIssuer,
    SpeechTuning,
)
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.errors import UpstreamError
from mochi_contracts import EventType, SessionMode, SessionState, SessionStatus


@dataclass(frozen=True)
class SessionConfig:
    """Agora-facing settings for one session (built from `Settings`)."""

    app_id: str
    channel: str
    pi_uid: int
    agent_uid: int
    token_ttl_seconds: int
    llm_url: str
    llm_key: str
    tuning: SpeechTuning


class SessionService:
    """`POST /api/sessions/demo/start` and `.../stop`."""

    def __init__(
        self,
        core: GatewayCore,
        agora: AgoraAgentClient,
        tokens: RtcTokenIssuer,
        config: SessionConfig,
    ) -> None:
        self._store = core.store
        self._hub = core.hub
        self._live_hint = core.live_hint
        self._clock = core.clock
        self._logger = core.logger
        self._agora = agora
        self._tokens = tokens
        self._config = config

    async def start(self) -> SessionState:
        """Start the agent and begin capturing. Idempotent; an Agora failure leaves no state."""
        if self._store.capturing:
            return self._store.session_state()
        agent_id = await self._start_agent()
        expires = self._clock.now() + timedelta(seconds=self._config.token_ttl_seconds)
        self._store.agent_id = agent_id
        self._store.pi_token = self._issue(self._config.pi_uid)
        self._store.pi_token_expires_at = expires
        self._store.status, self._store.capturing = SessionStatus.ACTIVE, True
        self._store.mode = SessionMode.TOGETHER
        return await self._publish_state()

    async def stop(self) -> SessionState:
        """Stop the agent and capturing. Idempotent; an agent that is already gone is fine."""
        agent_id = self._store.agent_id
        if agent_id is not None:
            await self._stop_agent(agent_id)
        self._store.agent_id, self._store.pi_token = None, None
        self._store.status, self._store.capturing = SessionStatus.ENDED, False
        await self._live_hint.clear()
        return await self._publish_state()

    def _issue(self, uid: int) -> str:
        return self._tokens.issue(self._config.channel, uid, self._config.token_ttl_seconds)

    async def _start_agent(self) -> str:
        request = AgentStartRequest(
            channel=self._config.channel,
            agent_uid=self._config.agent_uid,
            remote_uid=self._config.pi_uid,
            token=self._issue(self._config.agent_uid),
            llm_url=self._config.llm_url,
            llm_key=self._config.llm_key,
            tuning=self._config.tuning,
        )
        try:
            return await self._agora.start_agent(request)
        except AgoraError as error:
            self._logger.log("agora_start_failed", {"error": str(error)})
            raise UpstreamError(f"could not start the Agora agent: {error}") from error

    async def _stop_agent(self, agent_id: str) -> None:
        try:
            await self._agora.stop_agent(agent_id)
        except AgentAlreadyStopped:
            self._logger.log("agora_already_stopped", {"agent_id": agent_id})
        except AgoraError as error:
            # Stop locally anyway: the Pi must stop sending even if Agora is unreachable.
            self._logger.log("agora_stop_failed", {"agent_id": agent_id, "error": str(error)})

    async def _publish_state(self) -> SessionState:
        state = self._store.session_state()
        await self._hub.publish(EventType.SESSION_STATE_CHANGED, state)
        return state
