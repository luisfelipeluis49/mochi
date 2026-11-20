"""A device that runs the agent itself (`start` with `agent: device`) and reports what it hears."""

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_contracts import DecisionKind
from tests.harness import ANA, HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
ASK_MOCHI = "Oi Mochi, what's the word for fila?"
ON_DEVICE = {"agent": "device"}
STATE = "/api/devices/home_pi_01/state"
TURNS = "/api/devices/home_pi_01/turns"


def _client(env: dict[str, str] | None = None) -> tuple[TestClient, Harness]:
    harness = make_harness(env=env)
    return TestClient(create_app(harness.container)), harness


def test_device_run_session_starts_no_agora_agent_and_stops_without_one() -> None:
    client, harness = _client()
    started = client.post("/api/sessions/demo/start", json=ON_DEVICE).json()
    assert started["capturing"] is True and started["status"] == "active"
    assert harness.agora.started == []
    assert client.get(STATE).json()["capturing"] is True
    assert client.post("/api/sessions/demo/stop").json()["capturing"] is False
    assert harness.agora.stopped == []


def test_a_start_without_the_option_still_starts_the_backend_agent() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start", json=ON_DEVICE)
    client.post("/api/sessions/demo/stop")
    client.post("/api/sessions/demo/start", json={})
    assert len(harness.agora.started) == 1
    assert harness.container.core.store.agent_on_device is False


def test_a_sentence_the_device_reports_gets_its_hint() -> None:
    client, _ = _client()
    client.post("/api/sessions/demo/start", json=ON_DEVICE)
    reply = client.post(TURNS, json={"text": ADIAR}).json()
    assert reply["decision"]["decision"] == "SHOW_HINT"
    assert reply["decision"]["hint"]["expression"] == "postpone"


def test_reported_sentences_are_ignored_outside_a_session_and_from_unknown_devices() -> None:
    client, _ = _client()
    assert client.post(TURNS, json={"text": ADIAR}).json()["decision"]["decision"] == "IGNORE"
    assert client.post("/api/devices/pi_99/turns", json={"text": ADIAR}).status_code == 404


async def test_hint_reaches_the_screens_but_the_backend_says_nothing_itself() -> None:
    """The device's own agent answers, so no reply text and no `agent.speak.requested`."""
    harness = make_harness()
    await harness.container.sessions.start(agent_on_device=True)
    ana, home = await harness.connect_all(ANA, HOME)
    outcome = await harness.say(ASK_MOCHI)
    assert outcome.decision.decision is DecisionKind.SPEAK and outcome.reply == ""
    assert "hint.created" in ana.types() and "hint.created" in home.types()
    assert "agent.speak.requested" not in ana.types() + home.types()


def test_a_device_that_does_its_own_talking_is_never_muted() -> None:
    client, _ = _client({"MOCHI_SILENCE_STRATEGY": "mute_speaker"})
    client.post("/api/sessions/demo/start", json=ON_DEVICE)
    assert client.get(STATE).json()["speaker_muted"] is False
    client.post("/api/sessions/demo/stop")
    client.post("/api/sessions/demo/start")  # the backend's agent: muted until it should speak
    assert client.get(STATE).json()["speaker_muted"] is True


def test_default_ears_are_ares_in_english_and_portuguese() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    tuning = harness.agora.started[0].tuning
    assert (tuning.asr_vendor, tuning.asr_language) == ("ares", "en-US,pt-PT")
    assert tuning.asr_keywords == ("Mochi",) and tuning.asr_credential_mode == ""
