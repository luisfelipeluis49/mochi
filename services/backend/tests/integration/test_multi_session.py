"""Several sessions at once: a phone's never disturbs the Pi's (DECISIONS D-37)."""

import pytest
from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.client_port import AgoraError
from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.errors import ConflictError, NotFoundError
from mochi_backend.gateway.session_registry import SessionRuntime
from mochi_contracts import SessionStatus
from tests.harness import ANA, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
PHONE = "p-1"
ANA_PHONE = ConnectionTarget("mobile", user_id="ana", session_id=PHONE)
BEN_PHONE = ConnectionTarget("mobile", user_id="ben", session_id=PHONE)


async def _both_running() -> tuple[Harness, SessionRuntime]:
    harness = make_harness()
    await harness.container.sessions.start()  # the Pi's session
    phone = harness.container.registry.open(PHONE)
    await phone.sessions.start()
    return harness, phone


async def test_each_session_has_its_own_channel_and_turn_endpoint() -> None:
    harness, _ = await _both_running()
    pi, phone = harness.agora.started
    assert pi.channel == "mochi-demo" and pi.llm_url.endswith("/agora/llm/demo/chat/completions")
    assert phone.channel == "mochi-demo-p-1"
    assert phone.llm_url.endswith("/agora/llm/p-1/chat/completions")


async def test_the_phone_stopping_leaves_the_pi_capturing() -> None:
    harness, phone = await _both_running()
    await phone.sessions.stop()
    pi_state = harness.container.devices.state("home_pi_01")
    assert pi_state.capturing and pi_state.agora is not None
    assert pi_state.agora.channel == "mochi-demo"
    assert harness.agora.stopped == ["agent-2"]  # only the phone's agent


async def test_the_pi_stopping_leaves_the_phone_capturing() -> None:
    harness, phone = await _both_running()
    await harness.container.sessions.stop()
    assert phone.core.store.capturing
    assert harness.agora.stopped == ["agent-1"]


async def test_a_phone_sentence_makes_no_hint_on_the_pi() -> None:
    harness, phone = await _both_running()
    pi_home, ana_pi, ana_phone = (
        await harness.connect(ConnectionTarget("home", device_id="home_pi_01")),
        await harness.connect(ANA),
        await harness.connect(ANA_PHONE),
    )
    await phone.pipeline.handle_turn(ADIAR)
    assert "hint.created" in ana_phone.types()
    assert "hint.created" not in pi_home.types() and "hint.created" not in ana_pi.types()
    assert harness.container.core.store.hints == []  # the Pi's history is untouched


async def test_a_pi_sentence_makes_no_hint_on_the_phone() -> None:
    harness, _ = await _both_running()
    ana_phone = await harness.connect(ANA_PHONE)
    before = len(ana_phone.texts)
    await harness.container.pipeline.handle_turn(ADIAR)
    assert [t for t in ana_phone.types()[before:] if t.startswith("hint")] == []


async def test_a_word_saved_in_a_phone_session_is_in_every_session_and_only_ana_gets_it() -> None:
    harness, phone = await _both_running()
    ana_phone, ana_pi, ben_phone = await harness.connect_all(ANA_PHONE, ANA, BEN_PHONE)
    await phone.pipeline.handle_turn(ADIAR)
    assert "learning_event.created" in ana_phone.types()  # her phone session
    assert "learning_event.created" in ana_pi.types()  # her other connection: the same person
    assert "learning_event.created" not in ben_phone.types()
    words = harness.container.core.intelligence.words_for("ana")  # the Pi's brain sees it too
    assert [w.expression for w in words] == ["postpone"]


async def test_cooldown_is_per_session() -> None:
    harness, phone = await _both_running()
    first = await harness.container.pipeline.handle_turn(ADIAR)
    second = await phone.pipeline.handle_turn("I forgot my guarda-chuva at the office.")
    assert first.decision.hint is not None and second.decision.hint is not None


async def test_connecting_before_start_sees_an_idle_session_then_the_real_events() -> None:
    harness = make_harness()
    early = await harness.connect(ANA_PHONE)
    assert early.types()[0] == "session.state.changed"
    assert harness.container.registry.peek(PHONE) is None  # connecting opens nothing
    phone = harness.container.registry.open(PHONE)
    await phone.sessions.start()
    assert early.types().count("session.state.changed") == 2


async def test_stopping_closes_the_session_and_a_phone_never_closes_the_demo() -> None:
    harness, phone = await _both_running()
    client = TestClient(create_app(harness.container))
    assert client.post(f"/api/sessions/{PHONE}/stop").status_code == 200
    assert harness.container.registry.peek(PHONE) is None
    assert harness.container.registry.live_ids() == ["demo"]
    assert client.post("/api/sessions/demo/stop").json()["status"] == SessionStatus.ENDED.value
    assert harness.container.registry.peek("demo") is not None
    assert phone.core.store.status is SessionStatus.ENDED


async def test_unknown_sessions_are_404_and_bad_ids_are_rejected() -> None:
    client = TestClient(create_app(make_harness().container))
    assert client.post("/dev/sessions/nope/turn", json={"text": "hi"}).status_code in (404, 405)
    assert client.get("/api/sessions/nope/agora").status_code == 404
    assert client.post("/api/sessions/a.b/start").status_code == 422
    assert client.post("/api/sessions/" + "x" * 41 + "/start").status_code == 422


async def test_the_phone_gets_its_own_join_block_not_the_pis() -> None:
    harness, _ = await _both_running()
    client = TestClient(create_app(harness.container))
    join = client.get(f"/api/sessions/{PHONE}/agora").json()
    assert join["channel"] == "mochi-demo-p-1"


async def test_too_many_live_sessions_is_a_clear_conflict() -> None:
    harness = make_harness()
    for number in range(7):
        harness.container.registry.open(f"s{number}")
    with pytest.raises(ConflictError):
        harness.container.registry.open("one-too-many")
    with pytest.raises(NotFoundError):
        harness.container.registry.runtime("one-too-many")


async def test_a_failed_start_leaves_no_session_behind() -> None:
    harness = make_harness()
    harness.agora.start_error = AgoraError("down")
    client = TestClient(create_app(harness.container))
    assert client.post(f"/api/sessions/{PHONE}/start").status_code == 502
    assert harness.container.registry.peek(PHONE) is None
