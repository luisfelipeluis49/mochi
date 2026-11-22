"""Start/Stop/Reset races found in review: every test holds one call mid-flight with a gate."""

import asyncio

import pytest

from mochi_backend.gateway.errors import InvalidRequestError
from mochi_contracts import DecisionKind, SessionMode
from tests.fakes.fake_sender import FakeSender
from tests.fakes.held_sender import HeldSender
from tests.harness import ANA, AUDIENCE, HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."


async def test_two_simultaneous_starts_create_one_agent() -> None:
    harness = make_harness()
    harness.agora.start_gate = asyncio.Event()
    sessions = harness.container.sessions
    first = asyncio.create_task(sessions.start())
    await harness.agora.start_entered.wait()
    second = asyncio.create_task(sessions.start())
    await asyncio.sleep(0)  # let the second call reach the lock
    harness.agora.start_gate.set()
    await asyncio.gather(first, second)
    assert len(harness.agora.started) == 1
    assert harness.container.core.store.capturing


async def test_stop_during_start_leaves_capture_off_and_cleans_up_the_new_agent() -> None:
    harness = make_harness()
    harness.agora.start_gate = asyncio.Event()
    starting = asyncio.create_task(harness.container.sessions.start())
    await harness.agora.start_entered.wait()
    state = await harness.container.sessions.stop()
    harness.agora.start_gate.set()
    await starting
    store = harness.container.core.store
    assert not state.capturing and not store.capturing and store.agent_id is None
    assert harness.agora.stopped == ["agent-1"]


async def test_stop_turns_capture_off_before_waiting_for_agora() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    harness.agora.stop_gate = asyncio.Event()
    stopping = asyncio.create_task(harness.container.sessions.stop())
    await harness.agora.stop_entered.wait()
    device = harness.container.devices.state("home_pi_01")
    assert device.capturing is False and device.agora is None
    harness.agora.stop_gate.set()
    await stopping


@pytest.mark.parametrize("operation", ["stop", "reset"])
async def test_a_decision_in_flight_is_dropped_when_the_session_changes(operation: str) -> None:
    harness = make_harness(gated=True)
    assert harness.gate is not None
    await harness.container.sessions.start()
    clients = await harness.connect_all(HOME, AUDIENCE)
    seen = [len(c.texts) for c in clients]
    turn = asyncio.create_task(harness.say(ADIAR))
    await harness.gate.entered.wait()
    if operation == "stop":
        await harness.container.sessions.stop()
    else:
        await harness.container.demo_reset.run()
    after_change = [len(c.texts) for c in clients]
    harness.gate.gate.set()
    outcome = await turn
    assert outcome.reply == "" and outcome.decision.decision is DecisionKind.IGNORE
    assert [len(c.texts) for c in clients] == after_change and after_change >= seen
    assert not any(t.startswith("hint.") for c in clients for t in c.types()[len(seen) :])
    assert harness.container.core.intelligence.words_for("ana") == []


async def test_a_review_is_one_persons_and_the_next_session_is_a_meeting_again() -> None:
    harness = make_harness()
    state = await harness.container.sessions.start(mode=SessionMode.REVIEW, user_id="ben")
    assert (state.mode, state.participants) == (SessionMode.REVIEW, ["ben"])
    assert state.focus.value == "pt-BR"  # Ben's own target language
    context = harness.container.pipeline.build_context()
    assert [p.user_id for p in context.participants] == ["ben"]
    stopped = await harness.container.sessions.stop()
    assert (stopped.mode, stopped.participants) == (SessionMode.MEETING, ["ana", "ben"])
    await harness.container.sessions.start()
    outcome = await harness.say(ADIAR)
    assert outcome.decision.decision is DecisionKind.SHOW_HINT


async def test_a_review_needs_a_person_the_roster_knows() -> None:
    harness = make_harness()
    with pytest.raises(InvalidRequestError, match="known user_id"):
        await harness.container.sessions.start(mode=SessionMode.REVIEW, user_id="zed")
    with pytest.raises(InvalidRequestError, match="known user_id"):
        await harness.container.sessions.start(mode=SessionMode.REVIEW)
    assert harness.agora.started == [] and not harness.container.core.store.capturing


GUARDA_CHUVA = "I forgot my guarda-chuva at the office."
DEADLINE_SECONDS = 1.0  # a deadlock must fail the test, not hang the suite


async def _commit_in_flight(
    harness: Harness,
) -> tuple[HeldSender, FakeSender, asyncio.Task[object]]:
    """A turn whose commit is frozen mid-publish (the Ana client is holding its first message)."""
    held, observer = HeldSender(), FakeSender()
    hub = harness.container.core.hub
    hub.register(ANA, held)
    hub.register(HOME, observer)
    turn = asyncio.create_task(harness.say(ADIAR))
    await asyncio.wait_for(held.entered.wait(), DEADLINE_SECONDS)
    return held, observer, turn


@pytest.mark.parametrize("operation", ["stop", "reset"])
async def test_stop_and_reset_wait_for_a_commit_in_flight_and_nothing_follows_them(
    operation: str,
) -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    held, observer, turn = await _commit_in_flight(harness)
    change = (
        harness.container.sessions.stop()
        if operation == "stop"
        else harness.container.demo_reset.run()
    )
    changing = asyncio.create_task(change)
    await asyncio.sleep(0)
    held.release.set()
    await asyncio.wait_for(asyncio.gather(turn, changing), DEADLINE_SECONDS)
    assert observer.types()[-1] == "session.state.changed"  # nothing from the turn follows it
    assert observer.types().count("hint.created") == observer.types().count("hint.cleared")
    cards = harness.container.core.intelligence.words_for("ana")
    assert cards == [] if operation == "reset" else len(cards) == 1
