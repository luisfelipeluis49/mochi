"""One-touch assistance (DECISIONS D-59): after a hint, the whole sentence the speaker was reaching
for is suggested to them; one touch, and Mochi says it aloud so the meeting goes on.

The suggestion is worked out after the turn was committed, like an explanation (D-53), so the
hint itself never waits for it. Nothing is spoken unless someone asks: quiet by default holds.
"""

import asyncio
import json
from datetime import timedelta

from mochi_backend.gateway.agora.client_port import AgoraAgentClient, AgoraError
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.device_commands import DeviceCommand
from mochi_backend.platform.clock import iso_z, parse_iso_z
from mochi_contracts import (
    Decision,
    EventType,
    Hint,
    SessionContext,
    Speak,
    SpeakReason,
    SuggestedPhrase,
    Turn,
)


def suggest_card(phrase: SuggestedPhrase) -> str:
    """What the device shows for a suggested sentence, as JSON.

    Example: `{"hint_id": "hint_017", "text": "We need to unblock it.", "language": "en"}`.
    """
    card = {"hint_id": phrase.hint_id, "text": phrase.text, "language": phrase.language.value}
    return json.dumps(card, ensure_ascii=False)


class OneTouch:
    """Example: `one_touch.suggest_later(turn, context, decision, generation)` after a turn's
    commit; later `await one_touch.say("hint_017")` when someone touched the screen."""

    def __init__(
        self, core: GatewayCore, agora: AgoraAgentClient, *, enabled: bool, ttl_seconds: float
    ) -> None:
        self._core = core
        self._agora = agora
        self._enabled = enabled  # MOCHI_SUGGEST_PHRASES
        self._ttl = timedelta(seconds=ttl_seconds)
        self._live: SuggestedPhrase | None = None  # the one sentence that may be said now
        self._writing: set[asyncio.Task[None]] = set()

    def suggest_later(
        self, turn: Turn, context: SessionContext, decision: Decision, generation: int
    ) -> None:
        """Work out the sentence for a turn that got a silent hint, without making anything
        wait. A turn Mochi answered aloud needs none."""
        if not self._enabled or decision.hint is None or decision.speak is not None:
            return
        writing = asyncio.ensure_future(self._suggest(turn, context, decision.hint, generation))
        self._writing.add(writing)
        writing.add_done_callback(self._writing.discard)

    async def settle(self) -> None:
        """Wait for the suggestions being worked out (tests, and a clean shutdown)."""
        await asyncio.gather(*list(self._writing), return_exceptions=True)

    async def _suggest(
        self, turn: Turn, context: SessionContext, hint: Hint, generation: int
    ) -> None:
        try:
            sentence = await self._core.intelligence.suggest(turn, context, hint)
            await self._offer(hint, sentence, generation)
        except Exception as error:  # a suggestion that fails must cost nothing else
            self._core.logger.log("suggest_failed", {"hint_id": hint.hint_id, "error": repr(error)})

    async def _offer(self, hint: Hint, sentence: str | None, generation: int) -> None:
        if sentence is None:
            return
        async with self._core.commit:  # not in the middle of a turn, a Stop or a Reset
            await self._publish(hint, sentence, generation)

    async def _publish(self, hint: Hint, sentence: str, generation: int) -> None:
        store = self._core.store
        if generation != store.generation or not store.capturing:
            return  # the session it belonged to is over
        self._live = SuggestedPhrase(
            hint_id=hint.hint_id,
            target_user_id=hint.target_user_id,
            language=hint.target_language,
            text=sentence,
            expires_at=iso_z(self._core.clock.now() + self._ttl),
        )
        await self._core.hub.publish(EventType.PHRASE_SUGGESTED, self._live)
        core = self._core
        card = DeviceCommand(
            command_id=core.ids.new("cmd"),
            kind="suggest",
            value=suggest_card(self._live),
            at=core.clock.now(),
        )
        store.queue([card])
        core.logger.log("phrase_suggested", {"hint_id": hint.hint_id})

    def _sayable(self, hint_id: str) -> SuggestedPhrase | None:
        """The live suggestion when it is the one asked for, still fresh, in a running session."""
        phrase, store = self._live, self._core.store
        if phrase is None or phrase.hint_id != hint_id or not store.capturing:
            return None
        if self._core.clock.now() >= parse_iso_z(phrase.expires_at) or store.agent_id is None:
            return None
        return phrase

    async def say(self, hint_id: str) -> bool:
        """Someone touched: Mochi says the suggested sentence aloud, once. False when there is
        nothing (any more) to say for that hint, or Agora could not be told.

        Example: `await one_touch.say("hint_017")` -> True, and the room hears the sentence.
        """
        phrase, agent_id = self._sayable(hint_id), self._core.store.agent_id
        if phrase is None or agent_id is None:
            return False
        self._live = None  # once: a second touch says nothing
        try:
            await self._agora.speak(agent_id, phrase.text)
        except AgoraError as error:
            self._core.logger.log("agora_speak_failed", {"error": str(error)})
            return False
        speak = Speak(text=phrase.text, language=phrase.language, reason=SpeakReason.ASKS_MOCHI)
        await self._core.hub.publish(EventType.AGENT_SPEAK_REQUESTED, speak)
        self._core.silence.begin_speaking(phrase.text)
        self._core.logger.log("phrase_said", {"hint_id": hint_id})
        return True
