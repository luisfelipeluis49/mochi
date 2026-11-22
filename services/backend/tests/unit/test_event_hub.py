"""Hub behaviour found in review: ordered delivery, stalled clients, snapshots."""

import asyncio

from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.event_hub import BACKLOG_LIMIT, EventHub
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import EventPayload, EventType, Language, Speak, SpeakReason
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_sender import FakeEventLogger, FakeSender
from tests.fakes.held_sender import HeldSender

ANA = ConnectionTarget("mobile", user_id="ana")
BEN = ConnectionTarget("mobile", user_id="ben")
SPEAK = Speak(text="hi", language=Language.EN, reason=SpeakReason.ASKS_MOCHI)


def _hub(send_timeout_seconds: float = 1.0) -> tuple[EventHub, FakeEventLogger]:
    logger = FakeEventLogger()
    return EventHub(FakeClock(), SequentialIdGenerator(), logger, send_timeout_seconds), logger


class _NeverSender:
    """A phone that stopped reading: every send waits forever."""

    async def send_text(self, text: str) -> None:
        await asyncio.Event().wait()


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
    return [(EventType.SESSION_STATE_CHANGED, SessionStore().session_state())]


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
    assert newcomer.types() == ["session.state.changed", "agent.speak.requested"]
    assert [e.sequence for e in newcomer.events] == sorted(e.sequence for e in newcomer.events)


class _BadSender:
    """A client whose send fails in a way nobody listed."""

    async def send_text(self, text: str) -> None:
        raise ValueError("odd failure")


async def test_publish_returns_before_a_stalled_clients_send_timeout() -> None:
    logger = FakeEventLogger()
    hub = EventHub(FakeClock(), SequentialIdGenerator(), logger, 5.0).waiting_for_clients(0.01)
    healthy = FakeSender()
    hub.register(ANA, _NeverSender())
    hub.register(BEN, healthy)
    started = asyncio.get_running_loop().time()
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    assert asyncio.get_running_loop().time() - started < 1.0  # the send timeout is 5 s
    assert healthy.types() == ["agent.speak.requested"] * 2


async def test_a_stalled_client_in_one_session_does_not_delay_another_session() -> None:
    hub, _ = _hub()
    hub = hub.waiting_for_clients(0.01)
    other = hub.for_session("p-1")
    hub.register(ConnectionTarget("mobile", user_id="ana"), _NeverSender())
    healthy = FakeSender()
    other.register(ConnectionTarget("mobile", user_id="ben", session_id="p-1"), healthy)
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    await asyncio.wait_for(other.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK), 0.5)
    assert healthy.types() == ["agent.speak.requested"]


async def test_a_client_that_falls_too_far_behind_is_dropped() -> None:
    hub, logger = _hub()
    hub = hub.waiting_for_clients(0.0)
    hub.register(ANA, _NeverSender())
    for _ in range(BACKLOG_LIMIT + 2):
        await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    assert hub.connection_count == 0
    assert any(f.get("reason") == "backlog" for n, f in logger.lines if n == "connection_dropped")


async def test_a_sender_failing_in_an_unexpected_way_is_dropped_not_stuck() -> None:
    hub, logger = _hub()
    hub.register(ANA, _BadSender())
    await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    assert hub.connection_count == 0
    assert "connection_dropped" in logger.names()
