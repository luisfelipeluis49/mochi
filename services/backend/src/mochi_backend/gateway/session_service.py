"""Start and stop the session (and with it the Agora agent)."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStoppedError,
    AgentStartRequest,
    AgoraAgentClient,
    AgoraError,
    RtcTokenIssuer,
    SpeechTuning,
)
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.errors import UpstreamError
from mochi_contracts import EventType, GameState, SessionMode, SessionState, SessionStatus


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
    idle_timeout_seconds: int = 60


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
        self._silence = core.silence
        self._commit = core.commit
        self._clock = core.clock
        self._logger = core.logger
        self._agora = agora
        self._tokens = tokens
        self._config = config
        self._start_lock = asyncio.Lock()

    async def start(self) -> SessionState:
        """Start the agent and begin capturing. Idempotent; an Agora failure leaves no state."""
        async with self._start_lock:
            if self._store.capturing:
                return self._store.session_state()
            generation = self._store.generation
            agent_id = await self._start_agent()
            if generation != self._store.generation:
                self._logger.log("start_superseded", {"agent_id": agent_id})
                await self._stop_agent(agent_id)  # a Stop or Reset arrived while Agora was joining
                return self._store.session_state()
            self._begin(agent_id)
            return await self._publish_state()

    async def stop(self) -> SessionState:
        """Stop capturing at once, then the agent. Idempotent; a gone agent is fine."""
        self._store.invalidate()
        agent_id = self._store.agent_id
        was_playing = self._store.activity.state is not GameState.IDLE
        self._end_locally()
        async with (
            self._commit
        ):  # a turn that is mid-publish finishes first, then everything is cleared
            await self._live_hint.clear()
            state = await self._publish_state()
            if was_playing:
                await self._hub.publish(EventType.ACTIVITY_STATE_CHANGED, self._store.activity)
        if agent_id is not None:
            await self._stop_agent(agent_id)  # after local capture is off: the Pi sees false now
        return state

    def _begin(self, agent_id: str) -> None:
        expires = self._clock.now() + timedelta(seconds=self._config.token_ttl_seconds)
        self._store.agent_id = agent_id
        self._store.pi_token = self._issue(self._config.pi_uid)
        self._store.pi_token_expires_at = expires
        self._store.status, self._store.capturing = SessionStatus.ACTIVE, True
        self._store.unanswered = ""
        self._store.mode = SessionMode.TOGETHER

    def _end_locally(self) -> None:
        self._store.agent_id, self._store.pi_token = None, None
        self._store.unanswered = ""
        self._store.status, self._store.capturing = SessionStatus.ENDED, False
        self._store.end_game()  # an unfinished round must not keep the next session deaf
        self._hub.forget_secrets()
        self._silence.finished_speaking()  # a speaking window must not outlive the session

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
            idle_timeout_seconds=self._config.idle_timeout_seconds,
        )
        try:
            return await self._agora.start_agent(request)
        except AgoraError as error:
            self._logger.log("agora_start_failed", {"error": str(error)})
            raise UpstreamError(f"could not start the Agora agent: {error}") from error

    async def _stop_agent(self, agent_id: str) -> None:
        try:
            await self._agora.stop_agent(agent_id)
        except AgentAlreadyStoppedError:
            self._logger.log("agora_already_stopped", {"agent_id": agent_id})
        except AgoraError as error:
            # Stop locally anyway: the Pi must stop sending even if Agora is unreachable.
            self._logger.log("agora_stop_failed", {"agent_id": agent_id, "error": str(error)})

    async def _publish_state(self) -> SessionState:
        state = self._store.session_state()
        await self._hub.publish(EventType.SESSION_STATE_CHANGED, state)
        return state
