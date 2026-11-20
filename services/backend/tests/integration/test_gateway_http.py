"""The HTTP and WebSocket edges, through Starlette's TestClient (no network)."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.client_port import AgoraError
from mochi_backend.gateway.openai_sse import parse_stream
from tests.harness import Harness, make_harness

URL = "/agora/llm/demo/chat/completions"
KEY = {"x-mochi-key": "k"}


def _client(env: dict[str, str] | None = None) -> tuple[TestClient, Harness]:
    harness = make_harness(env={"MOCHI_ENABLE_DEV_ROUTES": "true", **(env or {})})
    return TestClient(create_app(harness.container)), harness


def _turn(text: str, stream: bool = True) -> dict[str, object]:
    return {
        "stream": stream,
        "messages": [{"role": "system", "content": "x"}, {"role": "user", "content": text}],
    }


def test_turn_endpoint_rejects_missing_or_wrong_key() -> None:
    client, _ = _client()
    assert client.post(URL, json=_turn("hi")).status_code == 401
    assert client.post(URL, json=_turn("hi"), headers={"x-mochi-key": "nope"}).status_code == 401
    assert (
        client.post(URL, json=_turn("hi"), headers={"authorization": "Bearer nope"}).status_code
        == 401
    )


def test_the_request_agora_documents_gets_a_200_stream_not_a_422() -> None:
    """Agora's documented custom-LLM body: extra top-level fields, message metadata, no `stream`."""
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    body = {
        "model": "mochi",
        "turn_id": 7,
        "timestamp": 1_763_615_000,
        "interruptable": True,
        "messages": [
            {"role": "system", "content": "You are an assistant."},
            {
                "role": "assistant",
                "content": "earlier",
                "turn_id": 6,
                "metadata": {"source": "llm"},
            },
            {
                "role": "user",
                "content": "I need to adiar my meeting tomorrow.",
                "turn_id": 7,
                "timestamp": 1_763_615_000,
                "metadata": {"source": "asr", "user": "user123", "nested": {"a": [1, 2]}},
            },
        ],
    }
    reply = client.post(URL, json=body, headers=KEY)
    assert reply.status_code == 200 and reply.headers["content-type"].startswith(
        "text/event-stream"
    )
    assert parse_stream(reply.text) == ("", True)  # a hint, so Mochi stays silent
    assert harness.container.core.store.turns[-1].text == "I need to adiar my meeting tomorrow."


def test_turn_endpoint_accepts_our_header_or_a_bearer_key() -> None:
    client, _ = _client()
    assert client.post(URL, json=_turn("hi"), headers=KEY).status_code == 200
    assert (
        client.post(URL, json=_turn("hi"), headers={"authorization": "Bearer k"}).status_code == 200
    )


def test_silent_turn_is_a_valid_empty_stream_and_a_spoken_turn_carries_the_text() -> None:
    client, _ = _client()
    client.post("/api/sessions/demo/start")
    silent = client.post(URL, json=_turn("I need to adiar my meeting"), headers=KEY)
    assert silent.headers["content-type"].startswith("text/event-stream")
    assert parse_stream(silent.text) == ("", True)
    spoken = client.post(URL, json=_turn("Oi Mochi, what's the word for recibo?"), headers=KEY)
    assert parse_stream(spoken.text) == ("You can say: receipt.", True)


def test_non_streaming_request_gets_a_plain_completion() -> None:
    client, _ = _client()
    body = client.post(URL, json=_turn("hi", stream=False), headers=KEY).json()
    assert body["choices"][0]["message"]["content"] == ""


def test_dev_turn_matches_the_agora_path_and_returns_the_decision() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    dev = client.post("/dev/sessions/demo/turn", json={"text": "I need to adiar my meeting"}).json()
    assert dev["reply"] == "" and dev["decision"]["decision"] == "SHOW_HINT"
    assert dev["decision"]["hint"]["expression"] == "postpone"
    assert harness.container.core.store.turns[-1].text == "I need to adiar my meeting"


def _events_ana_sees(route: str) -> list[str]:
    """Send the demo sentence through one real route and list what Ana's socket receives."""
    client, _ = _client()
    client.post("/api/sessions/demo/start")
    sentence = "I need to adiar my meeting"
    with client.websocket_connect("/ws?user=ana") as ana:
        snapshot = [ana.receive_json()["type"] for _ in range(2)]
        if route == "dev":
            client.post("/dev/sessions/demo/turn", json={"text": sentence})
        else:
            client.post(URL, json=_turn(sentence), headers=KEY)
        return snapshot + [ana.receive_json()["type"] for _ in range(2)]


def test_dev_route_and_agora_route_publish_the_same_events() -> None:
    dev, agora = _events_ana_sees("dev"), _events_ana_sees("agora")
    assert dev == agora
    assert dev[-2:] == ["learning_event.created", "hint.created"]


def test_a_binary_frame_does_not_leak_the_connection() -> None:
    client, harness = _client()
    hub = harness.container.core.hub
    with client.websocket_connect("/ws?user=ana") as ana:
        ana.receive_json()
        assert hub.connection_count == 1
        ana.send_bytes(b"\x00\x01")  # receive_text() used to raise KeyError here
    assert hub.connection_count == 0


def test_dev_route_is_absent_unless_enabled() -> None:
    harness = make_harness()
    client = TestClient(create_app(harness.container))
    assert client.post("/dev/sessions/demo/turn", json={"text": "hi"}).status_code == 404


def test_session_device_and_activity_endpoints() -> None:
    client, _ = _client()
    assert client.get("/api/devices/home_pi_01/state").json() == {
        "capturing": False,
        "agora": None,
        "speaker_muted": False,
    }
    started = client.post("/api/sessions/demo/start").json()
    assert started["capturing"] is True and started["status"] == "active"
    assert client.get("/api/devices/home_pi_01/state").json()["agora"]["channel"] == "mochi-demo"
    round_ = client.post("/api/sessions/demo/activity/start").json()
    assert round_["state"] == "ACTIVE_ROUND" and round_["revealed_word"] is None
    done = client.post("/api/sessions/demo/activity/result", json={"result": "guessed"}).json()
    assert done["state"] == "ROUND_RESULT" and done["revealed_word"] == "umbrella"
    assert client.post("/api/sessions/demo/stop").json()["capturing"] is False
    assert client.post("/api/demo/reset").json()["capturing"] is False


def test_error_statuses_are_readable() -> None:
    client, harness = _client()
    assert client.get("/api/devices/pi_99/state").status_code == 404
    conflict = client.post("/api/sessions/demo/activity/result", json={"result": "guessed"})
    assert conflict.status_code == 409 and "expected ACTIVE_ROUND" in conflict.json()["detail"]
    harness.agora.start_error = AgoraError("POST /join returned 401")
    bad = client.post("/api/sessions/demo/start")
    assert bad.status_code == 502 and "could not start the Agora agent" in bad.json()["detail"]


def test_health_and_readiness() -> None:
    client, _ = _client()
    assert client.get("/healthz").json()["status"] == "ok"
    ready = client.get("/readyz").json()
    assert ready["agora_mode"] == "fake" and ready["intelligence"] == "rules"
    assert ready["silence_strategy"] == "empty_reply"


def test_websocket_sends_the_snapshot_then_live_events_for_that_person_only() -> None:
    client, _ = _client()
    client.post("/api/sessions/demo/start")
    with (
        client.websocket_connect("/ws?user=ana") as ana,
        client.websocket_connect("/ws?user=ben") as ben,
    ):
        assert ana.receive_json()["type"] == "session.state.changed"
        assert ana.receive_json()["type"] == "activity.state.changed"
        ben.receive_json()
        ben.receive_json()
        client.post("/dev/sessions/demo/turn", json={"text": "I need to adiar my meeting"})
        # AGENTS 9.2 order: learning events are saved and published before the hint.
        assert [ana.receive_json()["type"], ana.receive_json()["type"]] == [
            "learning_event.created",
            "hint.created",
        ]
        client.post("/api/sessions/demo/stop")
        assert ben.receive_json()["type"] == "session.state.changed"  # first thing Ben gets after


@pytest.mark.parametrize("query", ["user=zed", "device=pi_99", "view=stage", ""])
def test_websocket_rejects_a_bad_query_with_4400_and_a_reason(query: str) -> None:
    client, _ = _client()
    with (
        client.websocket_connect(f"/ws?{query}") as socket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        socket.receive_text()
    assert closed.value.code == 4400 and "expected one of" in closed.value.reason
