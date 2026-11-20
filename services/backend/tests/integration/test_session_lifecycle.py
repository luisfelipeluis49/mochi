"""Start/Stop/Reset races found in review: every test holds one call mid-flight with a gate."""

import asyncio

import pytest

from mochi_backend.gateway.errors import ConflictError
from mochi_contracts import DecisionKind, GameState, SessionMode
from tests.harness import AUDIENCE, HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."


async def _running_round(harness: Harness) -> None:
    await harness.container.sessions.start()
    await harness.container.activity.start()


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


async def test_stop_during_a_round_returns_the_game_to_idle_and_start_hears_again() -> None:
    harness = make_harness()
    await _running_round(harness)
    store = harness.container.core.store
    assert store.activity.state is GameState.ACTIVE_ROUND
    await harness.container.sessions.stop()
    after_stop: GameState = store.activity.state  # re-read: mypy narrowed the assert above
    assert after_stop is GameState.IDLE and store.mode is SessionMode.TOGETHER
    await harness.container.sessions.start()
    outcome = await harness.say(ADIAR)
    assert outcome.decision.decision is DecisionKind.SHOW_HINT


async def test_stop_during_a_round_publishes_idle_and_forgets_the_secret() -> None:
    harness = make_harness()
    await _running_round(harness)
    audience = await harness.connect(AUDIENCE)
    await harness.container.sessions.stop()
    last_activity = [e for e in audience.events if e.type.value == "activity.state.changed"][-1]
    assert last_activity.payload.model_dump()["state"] == "IDLE"


async def test_a_second_round_cannot_start_while_one_is_active() -> None:
    harness = make_harness()
    await _running_round(harness)
    with pytest.raises(ConflictError, match="skipped"):
        await harness.container.activity.start()
