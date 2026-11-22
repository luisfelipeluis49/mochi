"""What the device tells us about itself, beyond polling its state (a proposal, see DECISIONS)."""

from datetime import timedelta

from mochi_backend.gateway.agora.client_port import AgoraAgentClient, AgoraError
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.errors import NotFoundError
from mochi_backend.gateway.roster import HOME_DEVICE_ID, Roster
from mochi_contracts import EventType, HeardPhrase, Language, Speak, SpeakReason

_VOICE_LINES = {
    (True, Language.PT_BR): "Pronto, {name}! Agora eu conheço a sua voz.",
    (True, Language.EN): "Got it, {name}! I know your voice now.",
    (False, Language.PT_BR): (
        "Desculpa, {name}, não ouvi o bastante. Pede de novo e fala um pouquinho mais."
    ),
    (False, Language.EN): (
        "Sorry, {name}, I didn't hear enough. Ask me again and talk a little longer."
    ),
}


def require_device(device_id: str) -> None:
    """Raise `NotFoundError` unless this is the one device we know."""
    if device_id != HOME_DEVICE_ID:
        raise NotFoundError(f"unknown device {device_id!r}; expected {HOME_DEVICE_ID!r}")


class DeviceLink:
    """`POST /api/devices/home_pi_01/status` and `.../voices`."""

    def __init__(self, core: GatewayCore, agora: AgoraAgentClient, roster: Roster) -> None:
        self._core = core
        self._agora = agora
        self._roster = roster

    def heard(self, phrases: list[HeardPhrase]) -> None:
        """The stretches of speech the device heard since its last report, each with who it was.

        They are what a sentence's speaker is worked out from (D-46). Not in a review, where
        every sentence is the reviewer's. Example: `heard([HeardPhrase(speaker="Ana",
        seconds=2.4, ago_ms=380)])`.
        """
        if self._core.store.reviewer is not None:
            return
        now = self._core.clock.now()
        for phrase in phrases:
            ended = now - timedelta(milliseconds=max(0, phrase.ago_ms))
            self._core.journal.phrase(self._roster.named(phrase.speaker), phrase.seconds, ended)

    def report(
        self, volume: int | None, temperature: float | None, voices: list[str], speaker: str | None
    ) -> None:
        """Pass on what the device knows about itself, so Mochi can talk about it.

        `speaker` is the name a voice was registered under; the person it belongs to is kept
        for the sentences that follow (`Turn.speaker_user_id`), except in a review, where every
        sentence is the reviewer's. Example: `report(80, 52.4, ["Ana"], "Ana")`.
        """
        if self._core.store.reviewer is None:
            self._core.store.speaker = self._roster.named(speaker)
        degrees = None if temperature is None else round(temperature)
        self._core.intelligence.device_status(volume, degrees, voices, speaker)

    async def voice_learned(self, name: str, language: Language, learned: bool) -> None:
        """Say out loud that a voice was learned, or that there was not enough of it."""
        line = _VOICE_LINES[(learned, language)].format(name=name)
        speak = Speak(text=line, language=language, reason=SpeakReason.ASKS_MOCHI)
        await self._core.hub.publish(EventType.AGENT_SPEAK_REQUESTED, speak)
        self._core.silence.begin_speaking(line)
        agent_id = self._core.store.agent_id
        if agent_id is None:
            return
        try:
            await self._agora.speak(agent_id, line)
        except AgoraError as error:
            self._core.logger.log("agora_speak_failed", {"error": str(error)})
