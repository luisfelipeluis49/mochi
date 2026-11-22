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
        snapshot = [ana.receive_json()["type"]]
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


def test_session_and_device_endpoints() -> None:
    client, _ = _client()
    assert client.get("/api/devices/home_pi_01/state").json() == {
        "capturing": False,
        "agora": None,
        "speaker_muted": False,
        "commands": [],
    }
    started = client.post("/api/sessions/demo/start").json()
    assert started["capturing"] is True and started["status"] == "active"
    assert client.get("/api/devices/home_pi_01/state").json()["agora"]["channel"] == "mochi-demo"
    assert started["mode"] == "meeting" and started["participants"] == ["ana", "ben"]
    assert client.post("/api/sessions/demo/activity/start").status_code == 404  # the game is gone
    assert client.post("/api/sessions/demo/stop").json()["capturing"] is False
    assert client.post("/api/demo/reset").json()["capturing"] is False


def _turn_texts(harness: Harness) -> list[object]:
    return [fields["text"] for name, fields in harness.logger.lines if name == "turn"]


def test_agora_repeats_unanswered_sentences_and_only_the_new_one_is_a_turn() -> None:
    """Seen live: after a silent reply the next request carries the old sentences too."""
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    first = "Yesterday I went to the fair with my mother."
    second = "I need to adiar my meeting tomorrow."
    for content in (first, f"{first}  {second}", f"{first}  {second}", f"{first}  {second}  Okay."):
        assert client.post(URL, json=_turn(content), headers=KEY).status_code == 200
    assert _turn_texts(harness) == [first, second, "Okay."]  # the exact repeat is not a turn


def test_after_mochi_spoke_the_next_message_is_taken_whole() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    ask = "Oi Mochi, what's the word for fila?"
    spoken, _ = parse_stream(client.post(URL, json=_turn(ask), headers=KEY).text)
    assert spoken == "You can say: queue."
    client.post(URL, json=_turn("Thank you."), headers=KEY)
    assert _turn_texts(harness) == [ask, "Thank you."]


def test_a_reply_the_person_talked_over_does_not_make_the_old_part_a_turn_again() -> None:
    """Seen live: Mochi answered "Like,." and the person kept talking; Agora sent both again."""
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    ask = "Oi Mochi, what's the word for fila?"
    client.post(URL, json=_turn(ask), headers=KEY)
    client.post(URL, json=_turn(f"{ask}  I mean the line of people."), headers=KEY)
    assert _turn_texts(harness) == [ask, "I mean the line of people."]


def test_what_mochi_said_is_in_the_log() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    client.post(URL, json=_turn("Oi Mochi, what's the word for fila?"), headers=KEY)
    replies = [fields for name, fields in harness.logger.lines if name == "reply"]
    assert replies == [{"text": "You can say: queue.", "commands": ""}]


def test_a_new_session_does_not_remember_the_last_ones_unanswered_sentences() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    client.post(URL, json=_turn("Nice weather today."), headers=KEY)
    client.post("/api/sessions/demo/stop")
    client.post("/api/sessions/demo/start")
    client.post(URL, json=_turn("Nice weather today. Really."), headers=KEY)
    assert _turn_texts(harness)[-1] == "Nice weather today. Really."


def test_without_a_model_key_the_ears_are_ares_with_the_lexicon_as_keywords() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    tuning = harness.agora.started[0].tuning
    assert (tuning.asr_vendor, tuning.asr_language) == ("ares", "en-US,pt-PT")
    assert tuning.asr_keywords[0] == "Mochi" and "guarda-chuva" in tuning.asr_keywords
    assert "umbrella" in tuning.asr_keywords and tuning.asr_credential_mode == ""
    assert len(harness.agora.attempts) == 1


def test_the_setting_that_lets_mochi_finish_its_answer_reaches_agora_with_either_ears() -> None:
    for extra in ({}, {"MODEL_API_KEY": "sk-test"}):
        client, harness = _client({"MOCHI_INTERRUPTION": "append", **extra})
        client.post("/api/sessions/demo/start")
        assert harness.agora.started[0].tuning.interruption == "append"
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    assert harness.agora.started[0].tuning.interruption == ""  # Agora's default, as before


def test_with_a_model_key_the_ears_are_openai_transcription_with_a_prompt() -> None:
    client, harness = _client({"MODEL_API_KEY": "sk-test"})
    client.post("/api/sessions/demo/start")
    tuning = harness.agora.started[0].tuning
    assert (tuning.asr_vendor, tuning.asr_language, tuning.asr_keywords) == ("openai", "en-US", ())
    listening = tuning.asr_params["input_audio_transcription"]
    assert isinstance(listening, dict) and listening["model"] == "gpt-4o-transcribe"
    assert listening["language"] == "en" and "guarda-chuva" in str(listening["prompt"])
    assert "never translate" in str(listening["prompt"])
    assert tuning.asr_params["api_key"] == "sk-test"


def test_when_agora_refuses_the_first_ears_the_session_starts_with_ares() -> None:
    client, harness = _client({"MODEL_API_KEY": "sk-test"})
    harness.agora.refused_ears = {"openai"}
    assert client.post("/api/sessions/demo/start").json()["capturing"] is True
    assert [r.tuning.asr_vendor for r in harness.agora.attempts] == ["openai", "ares"]
    assert harness.agora.started[0].tuning.asr_keywords[0] == "Mochi"
    assert "ears_fallback" in harness.logger.names()


def test_a_timeout_is_not_tried_again_with_other_ears() -> None:
    """The first agent may be running: a second start could put two agents in the channel."""
    client, harness = _client({"MODEL_API_KEY": "sk-test"})
    harness.agora.start_error = AgoraError("POST /join failed after 1 attempt: timeout")
    assert client.post("/api/sessions/demo/start").status_code == 502
    assert len(harness.agora.attempts) == 1


def test_error_statuses_are_readable() -> None:
    client, harness = _client()
    assert client.get("/api/devices/pi_99/state").status_code == 404
    review = client.post("/api/sessions/p-1/start", json={"mode": "review", "user_id": "zed"})
    assert review.status_code == 422 and "known user_id" in review.json()["detail"]
    assert harness.container.registry.peek("p-1") is None  # nothing was left behind
    conflict = client.get("/api/sessions/demo/agora")
    assert conflict.status_code == 409 and "not capturing" in conflict.json()["detail"]
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


def test_websocket_glasses_get_session_and_hints_only() -> None:
    client, _ = _client()
    client.post("/api/sessions/demo/start")
    with client.websocket_connect("/ws?user=ana&surface=ar") as glasses:
        assert glasses.receive_json()["type"] == "session.state.changed"
        client.post("/dev/sessions/demo/turn", json={"text": "I need to adiar my meeting"})
        assert glasses.receive_json()["type"] == "hint.created"  # no card


def test_websocket_unknown_surface_closes_4400_naming_it() -> None:
    client, _ = _client()
    with (
        client.websocket_connect("/ws?user=ana&surface=vr") as socket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        socket.receive_text()
    assert closed.value.code == 4400 and "'vr'" in closed.value.reason


@pytest.mark.parametrize("user", ["sophie", "x" * 200])
def test_websocket_bad_user_closes_4400_with_the_allowed_values_and_a_legal_reason(
    user: str,
) -> None:
    client, _ = _client()
    with (
        client.websocket_connect(f"/ws?user={user}&surface=ar") as socket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        socket.receive_text()
    reason = closed.value.reason
    assert closed.value.code == 4400
    assert "user=ana|ben" in reason and "device=home_pi_01" in reason and "view=audience" in reason
    assert (
        len(reason.encode()) <= 123
    )  # a longer close reason is a protocol error (client sees 1006)
