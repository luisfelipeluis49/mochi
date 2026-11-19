"""Describe & Guess endpoints (AGENTS 6.4, 7.5): start a round, record its result."""

from mochi_backend.gateway.agora.client_port import AgoraAgentClient, AgoraError
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.errors import ConflictError
from mochi_backend.gateway.turn_pipeline import TurnPipeline
from mochi_contracts import (
    Activity,
    ActivityCommand,
    ActivityResult,
    EventType,
    RoundResult,
    SessionMode,
    Speak,
)


class ActivityService:
    """Turns intelligence's `ActivityResult` into stored state, events and one spoken line."""

    def __init__(self, core: GatewayCore, pipeline: TurnPipeline, agora: AgoraAgentClient) -> None:
        self._store = core.store
        self._hub = core.hub
        self._intelligence = core.intelligence
        self._silence = core.silence
        self._logger = core.logger
        self._pipeline = pipeline
        self._agora = agora

    async def start(self) -> Activity:
        """Start a round: public state to everyone, the secret to the Home view only."""
        result = self._run(ActivityCommand(type="start", result=None))
        self._store.mode = SessionMode.ACTIVITY
        if result.private_prompt is not None:
            self._hub.protect_secret(result.private_prompt.secret_word)
        await self._publish_activity(result.activity)
        if result.private_prompt is not None:
            await self._hub.publish(EventType.ACTIVITY_PRIVATE_PROMPT, result.private_prompt)
        await self._announce(result.speak)
        await self._publish_session()
        return result.activity

    async def finish(self, outcome: RoundResult) -> Activity:
        """Record guessed/skipped: reveal the word, update cards, go back to `together`."""
        result = self._run(ActivityCommand(type="result", result=outcome))
        self._store.mode = SessionMode.TOGETHER
        await self._publish_activity(result.activity)
        await self._pipeline.save_learning_events(result.learning_events)
        await self._publish_session()
        return result.activity

    def _run(self, command: ActivityCommand) -> ActivityResult:
        try:
            return self._intelligence.handle(command, self._pipeline.build_context())
        except ValueError as error:
            raise ConflictError(str(error)) from error

    async def _publish_activity(self, activity: Activity) -> None:
        self._store.activity = activity
        await self._hub.publish(EventType.ACTIVITY_STATE_CHANGED, activity)

    async def _publish_session(self) -> None:
        await self._hub.publish(EventType.SESSION_STATE_CHANGED, self._store.session_state())

    async def _announce(self, speak: Speak | None) -> None:
        if speak is None:
            return
        await self._hub.publish(EventType.AGENT_SPEAK_REQUESTED, speak)
        self._silence.begin_speaking(speak.text)
        agent_id = self._store.agent_id
        if agent_id is None:
            return
        try:
            await self._agora.speak(agent_id, speak.text)
        except AgoraError as error:
            self._logger.log("agora_speak_failed", {"error": str(error)})
