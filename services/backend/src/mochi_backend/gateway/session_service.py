"""Start and stop the session (and with it the Agora agent)."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStoppedError,
    AgentStartRequest,
    AgoraAgentClient,
    AgoraError,
    AgoraRejectedError,
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
    fallback_tuning: SpeechTuning | None = None  # other ears, if Agora refuses the first ones
    greeting_en: str = ""
    greeting_pt: str = ""


# First words of a wake phrase that are Portuguese ("oi Mochi", "olá Mochi", "e aí Mochi").
PORTUGUESE_CUES = {"oi", "ola", "olá", "alo", "alô", "e", "ei", "bom", "boa"}


def greeting_for(woken_by: str | None, config: SessionConfig) -> str:
    """The greeting in the language Mochi was called in; "" when nobody called it.

    Example: `greeting_for("oi mochi", config)` is `config.greeting_pt`.
    """
    words = (woken_by or "").lower().split()
    if not words:
        return ""
    return config.greeting_pt if words[0] in PORTUGUESE_CUES else config.greeting_en


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
        self._intelligence = core.intelligence
        self._live_hint = core.live_hint
        self._silence = core.silence
        self._commit = core.commit
        self._clock = core.clock
        self._logger = core.logger
        self._agora = agora
        self._tokens = tokens
        self._config = config
        self._start_lock = asyncio.Lock()

    async def start(self, woken_by: str | None = None) -> SessionState:
        """Start the agent and begin capturing. Idempotent; an Agora failure leaves no state.

        `woken_by`: the wake phrase the device heard. Mochi then greets in that language, and the
        next sentence is meant for it.
        """
        async with self._start_lock:
            if self._store.capturing:
                return self._already_running(bool(woken_by))
            generation = self._store.generation
            agent_id = await self._start_agent(greeting_for(woken_by, self._config))
            if generation != self._store.generation:
                self._logger.log("start_superseded", {"agent_id": agent_id})
                await self._stop_agent(agent_id)  # a Stop or Reset arrived while Agora was joining
                return self._store.session_state()
            self._begin(agent_id)
            self._intelligence.session_started(bool(woken_by))
            return await self._publish_state()

    def _already_running(self, woken: bool) -> SessionState:
        if woken:  # called on the device while a session runs: Mochi listens to that person now
            self._intelligence.session_started(woken)
        return self._store.session_state()

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
        self._store.mode, self._store.commands = SessionMode.TOGETHER, []
        # The last session's sentences and hints are not this one's: a hint shown five minutes ago
        # must not count as "a hint in the last two turns" now.
        self._store.turns, self._store.hints = [], []
        self._store.last_heard = (-1, "")

    def _end_locally(self) -> None:
        self._store.agent_id, self._store.pi_token = None, None
        self._store.commands, self._store.last_heard = [], (-1, "")
        self._store.status, self._store.capturing = SessionStatus.ENDED, False
        self._store.end_game()  # an unfinished round must not keep the next session deaf
        self._hub.forget_secrets()
        self._silence.finished_speaking()  # a speaking window must not outlive the session

    def _issue(self, uid: int) -> str:
        return self._tokens.issue(self._config.channel, uid, self._config.token_ttl_seconds)

    async def _start_agent(self, greeting: str) -> str:
        """Start with the configured ears; if Agora refuses that request, with the fallback ears.

        Only a refusal (4xx) is tried again: after a timeout the first agent may be running.
        """
        fallback = self._config.fallback_tuning
        try:
            return await self._join(greeting, self._config.tuning)
        except AgoraRejectedError as error:
            if fallback is None:
                raise self._start_failed(error) from error
            self._logger.log("ears_fallback", {"to": fallback.asr_vendor, "because": str(error)})
        except AgoraError as error:
            raise self._start_failed(error) from error
        try:
            return await self._join(greeting, fallback)
        except AgoraError as error:
            raise self._start_failed(error) from error

    def _start_failed(self, error: AgoraError) -> UpstreamError:
        self._logger.log("agora_start_failed", {"error": str(error)})
        return UpstreamError(f"could not start the Agora agent: {error}")

    async def _join(self, greeting: str, tuning: SpeechTuning) -> str:
        request = AgentStartRequest(
            channel=self._config.channel,
            agent_uid=self._config.agent_uid,
            remote_uid=self._config.pi_uid,
            token=self._issue(self._config.agent_uid),
            llm_url=self._config.llm_url,
            llm_key=self._config.llm_key,
            tuning=tuning,
            idle_timeout_seconds=self._config.idle_timeout_seconds,
            greeting=greeting,
        )
        return await self._agora.start_agent(request)

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
