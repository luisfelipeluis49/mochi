"""Voices over HTTP (device key only), and words and voices surviving a restart."""

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.settings import DEV_DEVICE_KEY
from tests.fakes.fake_storage import FakeStorage
from tests.harness import make_harness

VOICES = "/api/devices/home_pi_01/voices"
KEY = {"Authorization": f"Bearer {DEV_DEVICE_KEY}"}
UPLOAD = {"language": "pt", "voiceprint": [0.01, -0.02, 0.03], "saved": "2026-11-21 15:00"}
ADIAR = "I need to adiar my meeting tomorrow."


def _client(storage: FakeStorage) -> TestClient:
    harness = make_harness(storage=storage, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    return TestClient(create_app(harness.container))


def test_every_voice_route_needs_the_device_key() -> None:
    client = _client(FakeStorage())
    assert client.get(VOICES).status_code == 401
    assert client.put(f"{VOICES}/Ana/voiceprint", json=UPLOAD).status_code == 401
    assert client.delete(f"{VOICES}/Ana").status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.get(VOICES, headers=wrong).status_code == 401


def test_a_voiceprint_is_stored_linked_to_its_user_and_listed() -> None:
    storage = FakeStorage()
    client = _client(storage)
    put = client.put(f"{VOICES}/Ana/voiceprint", json=UPLOAD, headers=KEY)
    assert put.status_code == 200 and put.json()["user_id"] == "ana"
    listed = client.get(VOICES, headers=KEY).json()
    assert [(v["name"], v["user_id"], v["voiceprint"]) for v in listed] == [
        ("Ana", "ana", [0.01, -0.02, 0.03])
    ]
    assert storage.voices["ana"].voiceprint == [0.01, -0.02, 0.03]


def test_a_bad_voiceprint_is_422_and_nothing_is_stored() -> None:
    storage = FakeStorage()
    client = _client(storage)
    empty = {**UPLOAD, "voiceprint": []}
    assert client.put(f"{VOICES}/Ana/voiceprint", json=empty, headers=KEY).status_code == 422
    body = '{"language": "pt", "voiceprint": [NaN], "saved": null}'
    nan = client.put(
        f"{VOICES}/Ana/voiceprint",
        content=body,
        headers={**KEY, "content-type": "application/json"},
    )
    assert nan.status_code == 422 and storage.voices == {}


def test_a_learned_voice_is_linked_and_a_forgotten_one_is_deleted() -> None:
    storage = FakeStorage()
    client = _client(storage)
    client.post("/api/sessions/demo/start")
    learned = {"name": "Ben", "language": "en", "learned": True}
    assert client.post(VOICES, json=learned, headers=KEY).status_code == 204
    assert storage.voices["ben"].user_id == "ben"
    assert client.delete(f"{VOICES}/Ben", headers=KEY).status_code == 204
    assert storage.voices == {} and client.get(VOICES, headers=KEY).json() == []


def test_a_failed_voice_enrollment_stores_nothing() -> None:
    storage = FakeStorage()
    client = _client(storage)
    failed = {"name": "Ben", "language": "en", "learned": False}
    assert client.post(VOICES, json=failed, headers=KEY).status_code == 204
    assert storage.voices == {}


def test_words_and_voices_survive_a_restart_and_reset_clears_only_words() -> None:
    storage = FakeStorage()
    client = _client(storage)
    client.post("/api/sessions/demo/start")
    client.post("/dev/sessions/demo/turn", json={"text": ADIAR})
    client.put(f"{VOICES}/Ana/voiceprint", json=UPLOAD, headers=KEY)
    assert [e.expression for e in storage.events.values()] == ["postpone"]

    restarted = make_harness(storage=storage)  # a new process, the same database
    words = restarted.container.core.intelligence.words_for("ana")
    assert [w.expression for w in words] == ["postpone"]
    assert [v.name for v in restarted.container.voices.all()] == ["Ana"]

    client.post("/api/demo/reset")
    assert storage.events == {} and "ana" in storage.voices


def test_readyz_says_whether_words_are_kept() -> None:
    assert _client(FakeStorage()).get("/readyz").json()["storage"] == "memory"
