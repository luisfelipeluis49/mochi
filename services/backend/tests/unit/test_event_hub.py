"""Hub behaviour found in review: whole-word secret guard, ordered delivery, stalled clients."""

import asyncio

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.session_store import idle_activity
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import EventPayload, EventType, Language, Speak, SpeakReason
from tests.factories import active_round
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_sender import FakeEventLogger, FakeSender
from tests.fakes.held_sender import HeldSender

ANA = ConnectionTarget("mobile", user_id="ana")
BEN = ConnectionTarget("mobile", user_id="ben")
AUDIENCE = ConnectionTarget("audience")
SPEAK = Speak(text="hi", language=Language.EN, reason=SpeakReason.ASKS_MOCHI)


def _hub(send_timeout_seconds: float = 1.0) -> tuple[EventHub, FakeEventLogger]:
    logger = FakeEventLogger()
    return EventHub(FakeClock(), SequentialIdGenerator(), logger, send_timeout_seconds), logger


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
    held, other = HeldSender(), FakeSender()
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


def _idle_snapshot() -> list[tuple[EventType, EventPayload]]:
    return [(EventType.ACTIVITY_STATE_CHANGED, idle_activity())]


class _DeadSender:
    """A client that is gone before the first byte."""

    def __init__(self) -> None:
        self.attempts = 0

    async def send_text(self, text: str) -> None:
        self.attempts += 1
        raise ConnectionError("client gone")


async def test_connecting_with_a_dead_client_stops_at_the_first_failed_snapshot_send() -> None:
    hub, _ = _hub()
    dead = _DeadSender()
    snapshot = [*_idle_snapshot(), *_idle_snapshot(), *_idle_snapshot()]
    assert await hub.connect(ANA, dead, lambda: snapshot) is None
    assert dead.attempts == 1  # no second and third send into a dead socket under the lock


async def test_a_snapshot_of_an_idle_game_does_not_end_the_protection_of_a_new_secret() -> None:
    hub, logger = _hub()
    audience = FakeSender()
    hub.protect_secret("umbrella")  # a round just started and its secret is protected
    await hub.connect(AUDIENCE, audience, _idle_snapshot)  # a late, stale IDLE snapshot
    leaky = active_round().model_copy(update={"public_instruction": "It is an umbrella"})
    await hub.publish(EventType.ACTIVITY_STATE_CHANGED, leaky)
    assert all("umbrella" not in text.lower() for text in audience.texts)
    assert "secret_leak_blocked" in logger.names()


async def test_a_client_that_connects_during_a_publish_sees_each_event_once_and_in_order() -> None:
    hub, _ = _hub()
    held, newcomer = HeldSender(), FakeSender()
    hub.register(ANA, held)
    publishing = asyncio.create_task(hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK))
    await asyncio.wait_for(held.entered.wait(), 1)
    connecting = asyncio.create_task(hub.connect(BEN, newcomer, _idle_snapshot))
    held.release.set()
    await asyncio.wait_for(asyncio.gather(publishing, connecting), 1)
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    assert newcomer.types() == ["activity.state.changed", "agent.speak.requested"]
    assert [e.sequence for e in newcomer.events] == sorted(e.sequence for e in newcomer.events)
