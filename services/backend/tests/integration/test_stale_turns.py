"""MOCHI_CANCEL_STALE_TURNS: a turn Agora gave up on stops deciding and leaves nothing behind."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.stale_turns import StaleTurns
from mochi_contracts import Decision, DecisionKind
from tests.harness import Harness, make_harness

ON = {"MOCHI_CANCEL_STALE_TURNS": "true"}
FIRST = "So yesterday."
BOTH = "So yesterday.  I need to adiar my meeting tomorrow"


def _turn_texts(harness: Harness) -> list[str]:
    return [str(fields["text"]) for event, fields in harness.logger.lines if event == "turn"]


async def _started(env: dict[str, str] | None) -> Harness:
    harness = make_harness(env=env, gated=True)
    await harness.container.sessions.start()
    return harness


async def test_a_newer_request_cancels_the_older_decide_and_covers_its_speech() -> None:
    harness = await _started(ON)
    assert harness.gate is not None
    pipeline = harness.container.pipeline
    older = asyncio.create_task(pipeline.handle_heard(FIRST, 0))
    await harness.gate.entered.wait()
    newer = asyncio.create_task(pipeline.handle_heard(BOTH, 0))
    dropped = await older
    assert dropped.stale and dropped.reply == ""
    assert dropped.decision.decision is DecisionKind.IGNORE
    harness.gate.gate.set()
    answered = await newer
    assert answered.decision.hint is not None and answered.decision.hint.expression == "postpone"
    assert "So yesterday." in _turn_texts(harness)[-1] and "adiar" in _turn_texts(harness)[-1]
    store = harness.container.core.store
    assert [t.segment_id for t in store.turns] == [answered.segment_id]  # nothing of the older
    whys = [f.get("why") for e, f in harness.logger.lines if e == "turn_dropped_stale"]
    assert whys == ["superseded"]


async def test_flag_off_keeps_todays_order_both_turns_decided() -> None:
    harness = await _started(None)
    assert harness.gate is not None
    pipeline = harness.container.pipeline
    older = asyncio.create_task(pipeline.handle_heard(FIRST, 0))
    await harness.gate.entered.wait()
    newer = asyncio.create_task(pipeline.handle_heard(BOTH, 0))
    harness.gate.gate.set()
    first, second = await older, await newer
    assert not first.stale and not second.stale
    assert _turn_texts(harness) == ["So yesterday.", "I need to adiar my meeting tomorrow"]
    assert second.decision.hint is not None


async def test_a_hang_up_cancels_the_deciding_and_leaves_nothing() -> None:
    harness = await _started(ON)
    assert harness.gate is not None
    hung_up = asyncio.Event()
    turn = asyncio.create_task(harness.container.pipeline.handle_heard(BOTH, 0, gone=hung_up.wait))
    await harness.gate.entered.wait()
    hung_up.set()
    outcome = await turn
    assert outcome.stale and outcome.reply == ""
    store = harness.container.core.store
    assert store.turns == [] and store.hints == [] and store.last_heard == (-1, "")
    assert harness.container.core.intelligence.words_for("ana") == []
    whys = [f.get("why") for e, f in harness.logger.lines if e == "turn_dropped_stale"]
    assert whys == ["disconnected"]


def test_the_agora_route_with_the_flag_on_still_answers() -> None:
    """The hang-up watcher must not fire on its own while the reply is being decided."""
    harness = make_harness(env=ON)
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    body = {"messages": [{"role": "user", "content": BOTH}], "stream": True}
    reply = client.post("/agora/llm/demo/chat/completions", json=body, headers={"x-mochi-key": "k"})
    assert reply.status_code == 200 and reply.text.endswith("data: [DONE]\n\n")
    assert [e for e, _ in harness.logger.lines if e == "turn_dropped_stale"] == []
    assert harness.container.core.store.hints[-1].expression == "postpone"


async def _never() -> Decision:
    await asyncio.Event().wait()
    raise AssertionError("unreachable")


async def test_cancelling_the_request_itself_is_passed_on() -> None:
    stale = StaleTurns(enabled=True)
    ticket = stale.arrive()
    running = asyncio.create_task(stale.decide(ticket, _never()))
    await asyncio.sleep(0)  # let it start waiting (a yield, not a timed sleep)
    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running
    assert ticket.deciding is not None and ticket.deciding.cancelled()


def test_a_request_that_waited_behind_a_newer_one_is_stale() -> None:
    stale = StaleTurns(enabled=True)
    waiting = stale.arrive()
    stale.arrive()
    assert stale.is_stale(waiting)
    assert not StaleTurns(enabled=False).is_stale(StaleTurns(enabled=False).arrive())


async def test_a_turn_that_already_spoke_is_never_cancelled() -> None:
    stale = StaleTurns(enabled=True)
    loop_future: asyncio.Future[Decision] = asyncio.get_running_loop().create_future()
    speaking = stale.arrive(spoken=lambda: True)
    speaking.deciding = loop_future
    stale.arrive()
    assert not loop_future.cancelled() and speaking.why is None
