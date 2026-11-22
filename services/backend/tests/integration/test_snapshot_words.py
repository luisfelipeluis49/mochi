"""A phone that connects gets its own person's saved words, so "My words" survives a restart."""

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from tests.fakes.fake_storage import FakeStorage
from tests.harness import make_harness

ADIAR = "I need to adiar my meeting tomorrow."


def _restarted_client() -> TestClient:
    storage = FakeStorage()
    first = TestClient(create_app(make_harness(storage=storage, env=_DEV).container))
    first.post("/api/sessions/demo/start")
    first.post("/dev/sessions/demo/turn", json={"text": ADIAR})
    return TestClient(create_app(make_harness(storage=storage, env=_DEV).container))  # restart


_DEV = {"MOCHI_ENABLE_DEV_ROUTES": "true"}


def test_a_phone_gets_its_saved_words_when_it_connects() -> None:
    client = _restarted_client()
    with client.websocket_connect("/ws?user=ana") as ana:
        events = [ana.receive_json() for _ in range(2)]
    assert [e["type"] for e in events] == ["session.state.changed", "learning_event.created"]
    assert events[1]["payload"]["expression"] == "postpone"


def test_another_person_gets_none_of_those_words() -> None:
    client = _restarted_client()
    with client.websocket_connect("/ws?user=ben") as ben:
        assert ben.receive_json()["type"] == "session.state.changed"
        client.post("/api/sessions/demo/start")
        assert ben.receive_json()["type"] == "session.state.changed"  # not a word


def test_the_projector_and_mochis_screen_get_no_words() -> None:
    client = _restarted_client()
    for route in ("/ws?view=audience", "/ws?device=home_pi_01"):
        with client.websocket_connect(route) as screen:
            assert screen.receive_json()["type"] == "session.state.changed"
            client.post("/api/sessions/demo/stop")
            assert screen.receive_json()["type"] == "session.state.changed"
