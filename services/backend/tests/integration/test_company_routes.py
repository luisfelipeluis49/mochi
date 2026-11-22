"""The company side over HTTP: who may see what, adding a member, voices that name the speaker."""

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.settings import DEV_DEVICE_KEY
from tests.fakes.fake_storage import FakeStorage
from tests.harness import Harness, make_harness

KEY = {"Authorization": f"Bearer {DEV_DEVICE_KEY}"}
ADIAR = "I need to adiar my meeting tomorrow."
CAIO_USER: dict[str, object] = {
    "user_id": "caio",
    "display_name": "Caio",
    "comfortable_languages": ["pt-BR"],
    "target_language": "en",
}
CAIO: dict[str, object] = {"user": CAIO_USER, "role": "member", "team": "Sales"}


def _client(storage: FakeStorage | None = None) -> tuple[TestClient, Harness]:
    harness = make_harness(env={"MOCHI_ENABLE_DEV_ROUTES": "true"}, storage=storage)
    return TestClient(create_app(harness.container)), harness


def _hears(client: TestClient, name: str | None) -> None:
    """The device reports whose registered voice it hears now."""
    body = {"volume": 60, "voices": ["Ana", "Caio"], "speaker": name}
    assert client.post("/api/devices/home_pi_01/status", json=body, headers=KEY).status_code == 204


def test_any_member_sees_who_belongs_and_only_an_administrator_sees_the_team() -> None:
    client, _ = _client()
    members = client.get("/api/companies/demo/members", params={"viewer": "ben"}).json()
    assert [(m["user"]["user_id"], m["role"]) for m in members] == [
        ("ana", "admin"),
        ("ben", "member"),
    ]
    for path in ("insights", "sessions"):
        assert (
            client.get(f"/api/companies/demo/{path}", params={"viewer": "ben"}).status_code == 403
        )
        assert (
            client.get(f"/api/companies/demo/{path}", params={"viewer": "ana"}).status_code == 200
        )
    assert client.get("/api/companies/demo/members").status_code == 403  # nobody in particular
    stranger = client.get("/api/companies/demo/members", params={"viewer": "zed"})
    assert stranger.status_code == 403 and "not a member" in stranger.json()["detail"]
    assert client.get("/api/companies/other/insights", params={"viewer": "ana"}).status_code == 404
    assert client.get("/api/companies/Bad Id/insights", params={"viewer": "ana"}).status_code == 422


def test_the_period_of_the_team_view_is_bounded() -> None:
    client, _ = _client()
    ask = {"viewer": "ana"}
    assert client.get("/api/companies/demo/insights", params=ask).json()["period_days"] == 30
    week = client.get("/api/companies/demo/insights", params={**ask, "days": 7}).json()
    assert week["period_days"] == 7 and len(week["weekly"]) in (1, 2)
    for days in (0, 366):
        refused = client.get("/api/companies/demo/insights", params={**ask, "days": days})
        assert refused.status_code == 422


def test_an_administrator_adds_a_member_who_can_then_connect_and_review() -> None:
    storage = FakeStorage()
    client, harness = _client(storage)
    refused = client.post("/api/companies/demo/members", params={"viewer": "ben"}, json=CAIO)
    assert refused.status_code == 403 and not harness.container.roster.knows("caio")
    added = client.post("/api/companies/demo/members", params={"viewer": "ana"}, json=CAIO)
    assert added.status_code == 200 and added.json() == CAIO
    assert [u.user_id for u in storage.users] == ["caio"] and ("demo", "caio") in storage.members
    with client.websocket_connect("/ws?user=caio") as phone:
        state = phone.receive_json()
        assert state["type"] == "session.state.changed"
        assert state["payload"]["participants"] == ["ana", "ben", "caio"]
    review = {"mode": "review", "user_id": "caio"}
    started = client.post("/api/sessions/p-caio/start", json=review).json()
    assert (started["mode"], started["participants"]) == ("review", ["caio"])
    bad = {**CAIO, "role": "owner"}
    assert (
        client.post("/api/companies/demo/members", params={"viewer": "ana"}, json=bad).status_code
        == 422
    )


def test_a_member_needs_an_id_the_other_routes_accept_and_a_name() -> None:
    client, harness = _client()
    for user_id in ("Caio Lima", "", "-caio", "caio/../x", "c" * 41):
        person = {**CAIO, "user": {**CAIO_USER, "user_id": user_id}}
        refused = client.post("/api/companies/demo/members", params={"viewer": "ana"}, json=person)
        assert refused.status_code == 422 and "bad user_id" in refused.json()["detail"]
    nameless = {**CAIO, "user": {**CAIO_USER, "display_name": "  "}}
    refused = client.post("/api/companies/demo/members", params={"viewer": "ana"}, json=nameless)
    assert refused.status_code == 422 and "empty display_name" in refused.json()["detail"]
    assert harness.container.roster.user_ids() == ["ana", "ben"]


def test_a_registered_voice_makes_the_hint_and_the_numbers_that_persons() -> None:
    client, harness = _client()
    client.post("/api/companies/demo/members", params={"viewer": "ana"}, json=CAIO)
    client.post("/api/sessions/demo/start")
    # Ana and Caio both learn English: without a voice, nobody in particular owns the word
    nobody = client.post("/dev/sessions/demo/turn", json={"text": ADIAR}).json()
    assert nobody["decision"]["hint"]["target_user_id"] is None
    _hears(client, "Caio")
    harness.clock.advance(120)
    for filler in ("That sounds busy.", "Yes, very."):  # the two-turn cooldown passes
        client.post("/dev/sessions/demo/turn", json={"text": filler})
    harness.clock.advance(120)
    heard = client.post(
        "/dev/sessions/demo/turn", json={"text": "I forgot my guarda-chuva at the office."}
    ).json()
    assert heard["decision"]["hint"]["target_user_id"] == "caio"
    _hears(client, "Somebody Else")  # a voice nobody registered
    assert harness.container.core.store.speaker is None
    client.post("/api/sessions/demo/stop")
    mine = client.get("/api/users/caio/moments", params={"viewer": "caio"}).json()
    assert [(m["expression"], m["user_id"]) for m in mine] == [("umbrella", "caio")]
    view = client.get("/api/companies/demo/insights", params={"viewer": "ana"}).json()
    rows = {row["user_id"]: row for row in view["members"]}
    assert (rows["caio"]["moments"], rows["caio"]["speaking_turns"], rows["caio"]["team"]) == (
        1,
        3,
        "Sales",
    )
    assert rows["caio"]["meetings"] == 1 and rows["ana"]["meetings"] == 0
    assert view["totals"]["active_members"] == 1 and view["totals"]["moments"] == 2
    [session] = client.get("/api/companies/demo/sessions", params={"viewer": "ana"}).json()
    assert {s["user_id"]: s["turns"] for s in session["speaking"]} == {None: 1, "caio": 3}


def test_a_persons_moments_are_theirs_alone() -> None:
    client, _ = _client()
    client.post("/api/sessions/demo/start")
    client.post("/dev/sessions/demo/turn", json={"text": ADIAR})
    assert (
        client.get("/api/users/ana/moments", params={"viewer": "ana"}).json()[0]["heard"] == ADIAR
    )
    for viewer in ("ben", "zed", None):
        params = {"viewer": viewer} if viewer else {}
        assert client.get("/api/users/ana/moments", params=params).status_code == 403
    assert client.get("/api/users/zed/moments", params={"viewer": "zed"}).status_code == 403
    client.post("/api/demo/reset")
    assert client.get("/api/users/ana/moments", params={"viewer": "ana"}).json() == []


def _heard(client: TestClient, *stretches: tuple[str | None, float, int]) -> None:
    """The device reports the stretches of speech it heard: (who, seconds, how many ms ago)."""
    heard = [{"speaker": who, "seconds": secs, "ago_ms": ago} for who, secs, ago in stretches]
    body = {"volume": 60, "voices": ["Ana", "Ben"], "speaker": None, "heard": heard}
    assert client.post("/api/devices/home_pi_01/status", json=body, headers=KEY).status_code == 204


def _say(client: TestClient, harness: Harness, text: str) -> None:
    harness.clock.advance(5)
    assert client.post("/dev/sessions/demo/turn", json={"text": text}).status_code == 200


def test_each_sentence_of_a_meeting_is_recorded_with_who_said_it() -> None:
    storage = FakeStorage()
    client, harness = _client(storage)
    client.post("/api/sessions/demo/start")
    harness.clock.advance(5)
    _heard(client, ("Ben", 1.8, 900))
    _say(client, harness, "Good morning, shall we start?")
    harness.clock.advance(5)
    _heard(client, ("Ana", 0.8, 2500), ("Ana", 2.6, 800))  # recognised early, then at her pause
    _say(client, harness, ADIAR)
    _say(client, harness, "Somebody said something the device never reported.")
    harness.clock.advance(5)
    _heard(client, ("A Visitor", 2.0, 700))  # a name no member has
    _say(client, harness, "Thanks for having me.")
    live = client.get("/dev/sessions/demo/transcript").json()
    assert [(u["user_id"], u["text"]) for u in live] == [
        ("ben", "Good morning, shall we start?"),
        ("ana", ADIAR),
        (None, "Somebody said something the device never reported."),
        (None, "Thanks for having me."),
    ]
    client.post("/api/sessions/demo/stop")
    mine = client.get("/api/users/ana/utterances", params={"viewer": "ana"}).json()
    assert [u["text"] for u in mine] == [ADIAR] and mine[0]["record_id"].startswith("rec_")
    assert client.get("/api/users/ana/utterances", params={"viewer": "ben"}).status_code == 403
    assert client.get("/api/users/ana/utterances").status_code == 403
    [session] = client.get("/api/companies/demo/sessions", params={"viewer": "ana"}).json()
    assert {s["user_id"]: s["turns"] for s in session["speaking"]} == {"ben": 1, "ana": 1, None: 2}
    assert [u.user_id for u in storage.utterances.values()] == ["ben", "ana", None, None]
    team = client.get("/api/companies/demo/insights", params={"viewer": "ana"})
    assert "Good morning" not in team.text and "adiar my meeting" not in team.text
    client.post("/api/demo/reset")
    assert client.get("/api/users/ana/utterances", params={"viewer": "ana"}).json() == []
    assert storage.utterances == {}


def test_the_hint_goes_to_the_person_the_device_heard_not_to_the_last_one_named() -> None:
    client, harness = _client()
    client.post("/api/companies/demo/members", params={"viewer": "ana"}, json=CAIO)
    client.post("/api/sessions/demo/start")
    _hears(client, "Ana")  # the name last shown on Mochi's face: Ana spoke a while ago
    harness.clock.advance(5)
    _heard(client, ("Caio", 2.4, 900))
    harness.clock.advance(1)
    said = client.post("/dev/sessions/demo/turn", json={"text": ADIAR}).json()
    assert said["decision"]["hint"]["target_user_id"] == "caio"


def test_a_review_is_recorded_as_its_persons_whatever_a_device_reports() -> None:
    client, harness = _client()
    review = {"mode": "review", "user_id": "ben"}
    client.post("/api/sessions/demo/start", json=review)
    harness.clock.advance(5)
    _heard(client, ("Ana", 2.0, 500))
    harness.clock.advance(1)
    client.post("/dev/sessions/demo/turn", json={"text": "Eu acho que sim."})
    assert [u["user_id"] for u in client.get("/dev/sessions/demo/transcript").json()] == ["ben"]


def test_a_status_report_with_a_runaway_list_or_a_bad_stretch_is_refused() -> None:
    client, _ = _client()
    too_many = [{"speaker": "Ana", "seconds": 1.0, "ago_ms": 1}] * 61
    for heard in (too_many, [{"speaker": "x" * 41, "seconds": 1.0, "ago_ms": 1}], [{"seconds": 1}]):
        refused = client.post("/api/devices/home_pi_01/status", json={"heard": heard}, headers=KEY)
        assert refused.status_code == 422


def test_in_a_noisy_room_only_registered_voices_count_when_asked_for() -> None:
    harness = make_harness(
        env={"MOCHI_ENABLE_DEV_ROUTES": "true", "MOCHI_MEETING_VOICES": "registered"}
    )
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    # before the device has reported any voice nothing is filtered (a phone never reports one)
    first = client.post("/dev/sessions/demo/turn", json={"text": "Good morning everyone."})
    assert first.status_code == 200
    harness.clock.advance(5)
    _heard(client, (None, 2.5, 800))  # the next table: a voice nobody registered
    _say(client, harness, "I forgot my guarda-chuva at the office.")
    harness.clock.advance(5)
    _heard(client, ("Ana", 2.4, 800))
    harness.clock.advance(1)
    hers = client.post("/dev/sessions/demo/turn", json={"text": ADIAR}).json()
    assert hers["decision"]["hint"]["expression"] == "postpone"
    said = client.get("/dev/sessions/demo/transcript").json()
    assert [u["text"] for u in said] == ["Good morning everyone.", ADIAR]  # the stranger: not kept
    assert "turn_ignored_unknown_voice" in harness.logger.names()
    words = harness.container.core.intelligence.words_for("ana")
    assert [w.expression for w in words] == ["postpone"]  # no umbrella from the next table
