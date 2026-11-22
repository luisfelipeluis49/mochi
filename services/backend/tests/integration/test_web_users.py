"""The web app's own users and sessions, end to end over HTTP and WebSocket (DECISIONS D-42)."""

import re

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.client_port import AgoraError
from mochi_backend.intelligence.word_owner import owner_for
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_storage import FakeStorage
from tests.harness import Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
WEB = "w-1a2b3c4d"
_DEV = {"MOCHI_ENABLE_DEV_ROUTES": "true"}


def _client(storage: FakeStorage | None = None) -> tuple[TestClient, Harness]:
    harness = make_harness(env=_DEV, storage=storage)
    return TestClient(create_app(harness.container)), harness


def _new_user(client: TestClient, name: str = "Luís Felipe", **languages: str) -> str:
    answer = client.post("/api/users", json={"display_name": name, **languages})
    assert answer.status_code == 201, answer.text
    user_id: str = answer.json()["user_id"]
    return user_id


def _start(client: TestClient, session: str, user_id: str | None) -> int:
    body = {"woken_by": "hey mochi", "user_id": user_id}
    status: int = client.post(f"/api/sessions/{session}/start", json=body).status_code
    return status


def test_create_and_read_a_user() -> None:
    client, _ = _client()
    created = client.post("/api/users", json={"display_name": "  Luís Felipe "})
    user = created.json()
    assert created.status_code == 201
    assert re.fullmatch(r"luis-felipe-[0-9a-f]{6}", user["user_id"])
    assert user == {
        "user_id": user["user_id"],
        "display_name": "Luís Felipe",
        "comfortable_languages": ["pt-BR"],
        "target_language": "en",
    }
    assert client.get(f"/api/users/{user['user_id']}").json() == user
    assert client.get("/api/users/ana").json()["display_name"] == "Ana"


@pytest.mark.parametrize("path", ["", "/words", "/sessions"])
def test_guest_and_unknown_users_are_404_and_bad_ids_422(path: str) -> None:
    client, _ = _client()
    assert client.get(f"/api/users/guest{path}").status_code == 404
    assert client.get(f"/api/users/nobody-000000{path}").status_code == 404
    assert client.get(f"/api/users/a.b{path}").status_code == 422
    answer = client.get("/api/users/nobody-000000" + path).json()
    assert isinstance(answer["detail"], str)


@pytest.mark.parametrize(
    "body",
    [
        {"display_name": "   "},
        {"display_name": "x" * 41},
        {"display_name": "Bad\u0007Name"},
        {"display_name": "Tab\tName"},
        {"display_name": "Luís", "comfortable_language": "fr"},
        {"display_name": "Luís", "comfortable_language": "en", "target_language": "en"},
        {"display_name": "Luís", "target_language": "pt-BR"},  # the default home is pt-BR too
        {},
    ],
)
def test_bad_new_users_are_422_in_fastapis_shape(body: dict[str, str]) -> None:
    client, _ = _client()
    answer = client.post("/api/users", json=body)
    assert answer.status_code == 422
    assert isinstance(answer.json()["detail"], list)


def test_a_web_session_is_the_users_and_guests_and_its_words_reach_only_them() -> None:
    client, _ = _client()
    user_id = _new_user(client)
    with (
        client.websocket_connect(f"/ws?user={user_id}&session={WEB}") as mine,
        client.websocket_connect("/ws?user=ana") as ana,
    ):
        assert [mine.receive_json()["type"] for _ in range(2)] == [
            "session.state.changed",
            "activity.state.changed",
        ]
        assert [ana.receive_json()["type"] for _ in range(2)][0] == "session.state.changed"
        started = client.post(f"/api/sessions/{WEB}/start", json={"user_id": user_id})
        assert started.json()["participants"] == [user_id, "guest"]
        assert started.json()["focus"] == "en"
        assert mine.receive_json()["payload"]["participants"] == [user_id, "guest"]
        client.post(f"/dev/sessions/{WEB}/turn", json={"text": ADIAR})
        word, hint = mine.receive_json(), mine.receive_json()
        assert word["type"] == "learning_event.created" and word["payload"]["user_id"] == user_id
        assert hint["type"] == "hint.created"
        assert hint["payload"]["target_user_id"] == user_id
        client.post("/api/sessions/demo/start")  # Ana's next event is this, not the web word
        assert ana.receive_json()["type"] == "session.state.changed"
    words = client.get(f"/api/users/{user_id}/words").json()
    assert [w["expression"] for w in words] == ["postpone"]
    assert client.get("/api/users/ana/words").json() == []


def test_a_user_at_home_in_english_makes_a_portuguese_focus_and_owns_its_words() -> None:
    client, harness = _client()
    user_id = _new_user(client, "Sam", comfortable_language="en", target_language="pt-BR")
    started = client.post(f"/api/sessions/{WEB}/start", json={"user_id": user_id})
    assert started.json()["focus"] == "pt-BR"
    context = harness.container.registry.runtime(WEB).pipeline.build_context()
    assert context.focus.value == "pt-BR" and owner_for(context) == user_id
    assert sorted(context.learning_events) == ["guest", user_id]


def test_stop_leaves_one_record_with_the_hints_words_and_minutes() -> None:
    client, harness = _client()
    user_id = _new_user(client)
    assert _start(client, WEB, user_id) == 200
    client.post(f"/dev/sessions/{WEB}/turn", json={"text": ADIAR})
    harness.clock.advance(750)  # the dev turn does not move the fake clock
    assert client.post(f"/api/sessions/{WEB}/stop", content=b"").status_code == 200  # a beacon
    assert client.post(f"/api/sessions/{WEB}/stop").status_code == 200
    [record] = client.get(f"/api/users/{user_id}/sessions").json()
    word_id = client.get(f"/api/users/{user_id}/words").json()[0]["learning_event_id"]
    assert record["session_id"] == WEB and record["user_id"] == user_id
    assert record["hint_count"] == 1 and record["learning_event_ids"] == [word_id]
    assert record["minutes"] == 12.5
    assert record["started_at"] == "2026-11-19T16:00:00.000Z"
    assert record["ended_at"] == "2026-11-19T16:12:30.000Z"
    assert set(record) == {
        "record_id",
        "session_id",
        "user_id",
        "started_at",
        "ended_at",
        "minutes",
        "hint_count",
        "learning_event_ids",
    }


def test_records_and_users_are_saved_and_come_back_after_a_restart() -> None:
    storage = FakeStorage()
    client, _ = _client(storage)
    user_id = _new_user(client, "Ana")
    _start(client, WEB, user_id)
    client.post(f"/api/sessions/{WEB}/stop")
    again, harness = _client(storage)  # restart over the same storage
    assert again.get(f"/api/users/{user_id}").status_code == 200
    assert len(again.get(f"/api/users/{user_id}/sessions").json()) == 1
    assert harness.container.voices.owner_of("Ana") == "ana"  # not the web user called Ana


def test_sessions_without_a_user_leave_no_record_and_reset_keeps_records() -> None:
    client, harness = _client()
    user_id = _new_user(client)
    _start(client, "w-00000001", None)
    client.post("/api/sessions/demo/start")
    client.post("/api/sessions/w-00000001/stop")
    client.post("/api/sessions/demo/stop")
    assert harness.container.history.for_user("ana") == []
    _start(client, WEB, user_id)
    client.post(f"/api/sessions/{WEB}/stop")
    client.post("/api/demo/reset")
    assert len(client.get(f"/api/users/{user_id}/sessions").json()) == 1


def test_an_evicted_user_session_leaves_its_record() -> None:
    client, harness = _client()
    user_id = _new_user(client)
    assert _start(client, WEB, user_id) == 200
    for number in range(7):  # demo + the web session + 6 = 8 live; the 7th evicts the oldest
        assert _start(client, f"s{number}", None) == 200
    assert WEB not in harness.container.registry.live_ids()
    [record] = client.get(f"/api/users/{user_id}/sessions").json()
    assert record["session_id"] == WEB


def test_start_refuses_a_user_on_demo_unknown_users_and_another_user() -> None:
    client, harness = _client()
    luis, sam = _new_user(client), _new_user(client, "Sam")
    assert _start(client, "demo", luis) == 409
    assert _start(client, "w-99999999", "nobody-000000") == 404
    assert _start(client, "w-99999999", "guest") == 404
    assert "w-99999999" not in harness.container.registry.live_ids()
    assert _start(client, WEB, luis) == 200
    assert _start(client, WEB, sam) == 409
    assert _start(client, WEB, luis) == 200
    assert _start(client, WEB, None) == 200
    assert harness.agora.started[-1].channel.endswith(WEB) and len(harness.agora.started) == 1


def test_a_bad_user_never_evicts_anyone_from_a_full_house() -> None:
    client, harness = _client()
    for number in range(7):
        assert _start(client, f"s{number}", None) == 200
    before = harness.container.registry.live_ids()
    assert len(before) == 8
    assert _start(client, "late", "nobody-000000") == 404
    assert harness.container.registry.live_ids() == before
    assert harness.agora.stopped == []


def test_a_failed_user_start_leaves_nothing_and_no_record() -> None:
    client, harness = _client()
    user_id = _new_user(client)
    harness.agora.start_error = AgoraError("down")
    assert _start(client, WEB, user_id) == 502
    assert harness.container.registry.peek(WEB) is None
    assert client.get(f"/api/users/{user_id}/sessions").json() == []


def test_the_snapshot_is_in_order_and_holds_only_the_users_own_words() -> None:
    client, _ = _client()
    user_id = _new_user(client)
    client.post("/api/sessions/demo/start")
    client.post("/dev/sessions/demo/turn", json={"text": ADIAR})  # a word for Ana
    _start(client, WEB, user_id)
    client.post(f"/dev/sessions/{WEB}/turn", json={"text": "I forgot my guarda-chuva."})
    with client.websocket_connect(f"/ws?user={user_id}&session={WEB}") as mine:
        events = [mine.receive_json() for _ in range(4)]
        client.post(f"/api/sessions/{WEB}/stop")
        rest = [mine.receive_json()["type"] for _ in range(2)]  # the hint goes, then the state
    assert [e["type"] for e in events] == [
        "session.state.changed",
        "activity.state.changed",
        "hint.created",
        "learning_event.created",
    ]
    assert events[3]["payload"]["user_id"] == user_id
    assert events[3]["payload"]["expression"] == "umbrella"
    assert rest == ["hint.cleared", "session.state.changed"]  # Ana's word never came
    assert all(e["session_id"] == WEB for e in events[:3])


@pytest.mark.parametrize("user", ["guest", "nobody-000000"])
def test_guest_and_unknown_users_cannot_connect(user: str) -> None:
    client, _ = _client()
    with (
        client.websocket_connect(f"/ws?user={user}&session={WEB}") as socket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        socket.receive_text()
    assert closed.value.code == 4400
    assert "user=ana|ben|<user_id>" in closed.value.reason


def test_a_word_the_guest_would_own_reaches_the_person_in_the_language_they_practise() -> None:
    # Sam is at home in English and practises Portuguese, and says "adiar" in an English sentence.
    # The rules give "postpone (adiar)" to the guest, who is nobody. Sam needs "adiar" (what Sam is
    # learning), with "postpone" as its meaning (D-44).
    client, harness = _client()
    sam = _new_user(client, "Sam", comfortable_language="en", target_language="pt-BR")
    client.post(f"/api/sessions/{WEB}/start", json={"user_id": sam})
    client.post(f"/dev/sessions/{WEB}/turn", json={"text": ADIAR})
    shown = harness.container.registry.runtime(WEB).core.live_hint.current
    assert shown is not None and shown.target_user_id == sam
    assert (shown.expression, shown.meaning, shown.target_language.value) == (
        "adiar",
        "postpone",
        "pt-BR",
    )
    [word] = client.get(f"/api/users/{sam}/words").json()
    assert (word["expression"], word["meaning"], word["target_language"]) == (
        "adiar",
        "postpone",
        "pt-BR",
    )
    assert client.get("/api/users/ana/words").json() == []


def test_a_phrase_papear_teaches_becomes_something_to_practise() -> None:
    # The person asks how to say a phrase; Papear answers with it and tags it, silently (D-45).
    line = (
        "[mood happy] You can say: my sneakers are nice."
        "[phrase: my sneakers are nice | meus tênis são bonitos] Now try it about your own shoes."
    )
    harness = make_harness(env=_DEV, character=FakeCharacterModel(line))
    client = TestClient(create_app(harness.container))
    luis = _new_user(client, "Luis")
    _start(client, WEB, luis)
    turn = client.post(
        f"/dev/sessions/{WEB}/turn", json={"text": "Como é que eu falo que meus tênis são bonitos?"}
    ).json()
    assert "[" not in turn["reply"] and "phrase" not in turn["reply"]  # never spoken
    [saved] = client.get(f"/api/users/{luis}/words").json()
    assert saved["expression"] == "my sneakers are nice"
    assert (saved["meaning"], saved["target_language"], saved["hint_id"]) == (
        "meus tênis são bonitos",
        "en",
        None,
    )
    assert saved["learning_state"] == "DISCOVERED" and saved["detection_signal"] == "asks_mochi"
    client.post(
        f"/dev/sessions/{WEB}/turn", json={"text": "Como é que eu falo que meus tênis são bonitos?"}
    )
    assert len(client.get(f"/api/users/{luis}/words").json()) == 1  # said twice: one card


IDIOM = "Honestly it is raining cats and dogs outside today."
EXPLAINED = (
    '[mood curious] "Raining cats and dogs" means raining very hard.'
    "[phrase: raining cats and dogs | chovendo muito]"
)


def _quiet_web(character: FakeCharacterModel) -> tuple[TestClient, Harness, str]:
    harness = make_harness(env=_DEV, character=character)
    client = TestClient(create_app(harness.container))
    person = _new_user(client, "Luis")
    started = client.post(f"/api/sessions/{WEB}/start", json={"user_id": person})  # not woken
    assert started.status_code == 200
    return client, harness, person


def test_a_quiet_web_session_explains_an_idiom_without_being_asked_and_saves_it() -> None:
    character = FakeCharacterModel(EXPLAINED)
    client, _, person = _quiet_web(character)
    turn = client.post(f"/dev/sessions/{WEB}/turn", json={"text": IDIOM}).json()
    assert turn["decision"]["decision"] == "SPEAK"
    assert "very hard" in turn["reply"] and "phrase" not in turn["reply"]
    assert character.requests[0].explains and not character.requests[0].woken
    [saved] = client.get(f"/api/users/{person}/words").json()
    assert saved["expression"] == "raining cats and dogs"


def test_a_quiet_web_session_says_nothing_when_nothing_needs_explaining() -> None:
    character = FakeCharacterModel("[quiet]")
    client, _, person = _quiet_web(character)
    turn = client.post(
        f"/dev/sessions/{WEB}/turn", json={"text": "We are going to the park later."}
    )
    assert turn.json()["decision"]["decision"] == "IGNORE" and turn.json()["reply"] == ""
    assert client.get(f"/api/users/{person}/words").json() == []
    short = client.post(f"/dev/sessions/{WEB}/turn", json={"text": "Yes, of course."})
    assert short.json()["decision"]["decision"] == "IGNORE"
    assert len(character.requests) == 1  # a short sentence is never worth a model call


def test_the_pi_and_a_woken_web_session_do_not_explain_on_their_own() -> None:
    character = FakeCharacterModel(EXPLAINED)
    harness = make_harness(env=_DEV, character=character)
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")  # the Pi's: nobody woke it, two people talk
    pi = client.post("/dev/sessions/demo/turn", json={"text": IDIOM}).json()
    assert pi["decision"]["decision"] == "IGNORE" and character.requests == []
    person = _new_user(client, "Luis")
    _start(client, WEB, person)  # woken ("hey mochi"): it is a conversation
    client.post(f"/dev/sessions/{WEB}/turn", json={"text": IDIOM})
    assert character.requests and character.requests[0].woken and not character.requests[0].explains
