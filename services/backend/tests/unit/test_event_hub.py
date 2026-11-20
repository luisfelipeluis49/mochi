"""Hub behaviour found in review: whole-word secret guard, ordered delivery, stalled clients."""

import asyncio

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import EventType, Language, Speak, SpeakReason
from tests.factories import active_round
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_sender import FakeEventLogger, FakeSender

ANA = ConnectionTarget("mobile", user_id="ana")
BEN = ConnectionTarget("mobile", user_id="ben")
AUDIENCE = ConnectionTarget("audience")
SPEAK = Speak(text="hi", language=Language.EN, reason=SpeakReason.ASKS_MOCHI)


def _hub(send_timeout_seconds: float = 1.0) -> tuple[EventHub, FakeEventLogger]:
    logger = FakeEventLogger()
    return EventHub(FakeClock(), SequentialIdGenerator(), logger, send_timeout_seconds), logger


class _HeldSender:
    """Blocks its first message until `release` is set, then records everything in order."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.sequences: list[int] = []
        self._first = True

    async def send_text(self, text: str) -> None:
        if self._first:
            self._first = False
            await self.release.wait()
        after_key = text.split('"sequence":')[1]
        self.sequences.append(int(after_key.split(",")[0].strip("}")))


class _NeverSender:
    """A phone that stopped reading: every send waits forever."""

    async def send_text(self, text: str) -> None:
        await asyncio.Event().wait()


async def test_a_secret_that_is_also_a_json_key_does_not_block_the_audience() -> None:
    hub, logger = _hub()
    audience = FakeSender()
    hub.register(AUDIENCE, audience)
    for word in ("state", "round", "activity", "hint", "part"):
        hub.protect_secret(word)
    await hub.publish(EventType.ACTIVITY_STATE_CHANGED, active_round())
    assert audience.types() == ["activity.state.changed"]
    assert "Ben describes. Ana guesses!" in audience.texts[0]
    assert "secret_leak_blocked" not in logger.names()


async def test_a_secret_inside_public_text_is_still_blocked_as_a_whole_word() -> None:
    hub, logger = _hub()
    audience = FakeSender()
    hub.register(AUDIENCE, audience)
    hub.protect_secret("umbrella")
    leaky = active_round().model_copy(update={"public_instruction": "Ben describes an Umbrella!"})
    await hub.publish(EventType.ACTIVITY_STATE_CHANGED, leaky)
    assert "umbrella" not in audience.texts[0].lower()
    assert "secret_leak_blocked" in logger.names()


async def test_concurrent_publishes_reach_every_client_in_sequence_order() -> None:
    hub, _ = _hub()
    held, other = _HeldSender(), FakeSender()
    hub.register(ANA, held)
    hub.register(BEN, other)
    first = asyncio.create_task(hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK))
    second = asyncio.create_task(hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK))
    await asyncio.sleep(0)
    held.release.set()
    await asyncio.gather(first, second)
    assert held.sequences == [1, 2]
    assert [e.sequence for e in other.events] == [1, 2]


async def test_a_stalled_client_is_dropped_and_does_not_block_the_others() -> None:
    hub, logger = _hub(send_timeout_seconds=0.01)
    healthy = FakeSender()
    hub.register(ANA, _NeverSender())
    hub.register(BEN, healthy)
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    assert healthy.types() == ["agent.speak.requested"] * 2
    assert "connection_dropped" in logger.names()
