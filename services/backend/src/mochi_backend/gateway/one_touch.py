"""The sentence after a hint (DECISIONS D-59, D-70): after a silent hint, the whole sentence the
speaker was reaching for is shown to them.

The suggestion is worked out after the turn was committed, like an explanation (D-53), so the
hint itself never waits for it. It is only shown. Until D-70 a touch on Mochi's screen made
Mochi say it; that is gone: a word someone asks for is now said at once (`decision_flow`).
"""

import asyncio
import json
from datetime import timedelta

from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.device_commands import DeviceCommand
from mochi_backend.platform.clock import iso_z
from mochi_contracts import (
    Decision,
    EventType,
    Hint,
    SessionContext,
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
    commit. (The name is from D-59, when a touch said the sentence.)"""

    def __init__(self, core: GatewayCore, *, enabled: bool, ttl_seconds: float) -> None:
        self._core = core
        self._enabled = enabled  # MOCHI_SUGGEST_PHRASES
        self._ttl = timedelta(seconds=ttl_seconds)  # how long a screen shows it
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
        phrase = SuggestedPhrase(
            hint_id=hint.hint_id,
            target_user_id=hint.target_user_id,
            language=hint.target_language,
            text=sentence,
            expires_at=iso_z(self._core.clock.now() + self._ttl),
        )
        await self._core.hub.publish(EventType.PHRASE_SUGGESTED, phrase)
        core = self._core
        card = DeviceCommand(
            command_id=core.ids.new("cmd"),
            kind="suggest",
            value=suggest_card(phrase),
            at=core.clock.now(),
        )
        store.queue([card])
        core.logger.log("phrase_suggested", {"hint_id": hint.hint_id})
