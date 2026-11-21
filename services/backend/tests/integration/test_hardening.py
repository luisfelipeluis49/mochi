"""Review fixes: device key, secret word, stale commands, rounds need a session, log redaction."""

import json

import pytest
from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.rest_client import AgoraRestClient
from mochi_backend.gateway.errors import ConflictError
from mochi_backend.platform.http_client import HttpResponse
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.settings import DEV_DEVICE_KEY, SettingsError, load_settings
from mochi_contracts import RoundResult
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.harness import ANA, HOME, Harness, make_harness
from tests.unit.test_gateway_rules import REQUEST

GUARDA_CHUVA = "I forgot my guarda-chuva at the office."
GOOD = {"Authorization": f"Bearer {DEV_DEVICE_KEY}"}
STATUS = "/api/devices/home_pi_01/status"
VOICES = "/api/devices/home_pi_01/voices"
LEARNED = {"name": "Ana", "language": "pt", "learned": True}


def _client() -> TestClient:
    return TestClient(create_app(make_harness().container))


# --- item 3: device key -------------------------------------------------------------------------


@pytest.mark.parametrize("path", [STATUS, VOICES])
def test_device_posts_need_the_device_key(path: str) -> None:
    client = _client()
    body = {"volume": 5} if path == STATUS else LEARNED
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert (
        client.post(path, json=body, headers={"Authorization": DEV_DEVICE_KEY}).status_code == 401
    )
    odd = {"Authorization": "Bearer caf\xe9".encode("latin-1")}
    assert client.post(path, json=body, headers=odd).status_code == 401
    assert client.post(path, json=body, headers=GOOD).status_code == 204


def test_a_missing_key_is_401_even_when_the_body_is_invalid() -> None:
    client = _client()
    assert client.post(VOICES, json={"name": 5}).status_code == 401
    assert client.post(STATUS, json={"volume": "loud"}).status_code == 401


def test_voice_names_and_lists_are_bounded() -> None:
    client = _client()
    for name in ["x" * 41, "Ana<script>", "", "Ana\nBen", "Ana 123"]:
        reply = client.post(VOICES, json={**LEARNED, "name": name}, headers=GOOD)
        assert reply.status_code == 422, name
    for name in ["Ana", "Mary Jane", "D'Arcy", "Jean-Luc", "José", "x" * 40]:
        reply = client.post(VOICES, json={**LEARNED, "name": name}, headers=GOOD)
        assert reply.status_code == 204, name
    assert client.post(STATUS, json={"voices": ["A"] * 9}, headers=GOOD).status_code == 422
    assert client.post(STATUS, json={"voices": ["A" * 41]}, headers=GOOD).status_code == 422
    assert client.post(STATUS, json={"voices": ["A"] * 8}, headers=GOOD).status_code == 204


def test_the_device_key_is_required_in_real_mode() -> None:
    real = {
        "MOCHI_AGORA_MODE": "real",
        "AGORA_APP_ID": "a",
        "AGORA_APP_CERTIFICATE": "b",
        "AGORA_REST_KEY": "c",
        "AGORA_REST_SECRET": "d",
        "MOCHI_TURN_KEY": "e",
        "MOCHI_PUBLIC_URL": "https://mochi.example",
    }
    with pytest.raises(SettingsError, match="MOCHI_DEVICE_KEY"):
        load_settings(real)
    assert load_settings({**real, "MOCHI_DEVICE_KEY": "f"}).mochi_device_key == "f"
    assert load_settings({"MOCHI_AGORA_MODE": "fake"}).mochi_device_key == DEV_DEVICE_KEY


# --- item 16 ------------------------------------------------------------------------------------


async def test_a_round_cannot_start_without_a_live_session() -> None:
    harness = make_harness()
    with pytest.raises(ConflictError, match="not capturing"):
        await harness.container.activity.start()
    assert harness.container.core.store.activity.state.value == "IDLE"


# --- item 4: the secret word --------------------------------------------------------------------


async def _round_on_umbrella(character: FakeCharacterModel | None) -> Harness:
    harness = make_harness(character=character)
    await harness.container.sessions.start()
    await harness.say(GUARDA_CHUVA)
    await harness.container.activity.start()
    assert harness.container.core.store.activity.state.value == "ACTIVE_ROUND"
    return harness


@pytest.mark.parametrize(
    "line", ["Yes, umbrella!", "It is an Umbrélla.", "[show umbrella] Sure!", "Sim: guarda-chuva!"]
)
async def test_a_spoken_reply_never_gives_the_secret_away(line: str) -> None:
    harness = await _round_on_umbrella(FakeCharacterModel(line))
    ana, home = await harness.connect(ANA), await harness.connect(HOME)
    store = harness.container.core.store
    cut = (len(ana.texts), len(home.texts), len(store.commands))
    outcome = await harness.say("Oi Mochi, is it an umbrella?")
    assert outcome.reply == "" and outcome.decision.decision.value == "IGNORE"
    assert (len(ana.texts), len(home.texts), len(store.commands)) == cut
    blocked = [f for name, f in harness.logger.lines if name == "secret_leak_blocked"]
    assert blocked and all("channel" in f for f in blocked)
    assert all("umbrella" not in json.dumps(f).lower() for f in blocked)


async def test_a_hint_never_gives_the_secret_away_in_either_language() -> None:
    harness = await _round_on_umbrella(FakeCharacterModel("Hmm."))
    ana = await harness.connect(ANA)
    cut = len(ana.texts)
    outcome = await harness.say("Oi Mochi, como se diz guarda-chuva?")
    assert outcome.reply == "" and outcome.decision.hint is None
    assert len(ana.texts) == cut
    assert "secret_leak_blocked" in harness.logger.names()


async def test_after_the_round_the_word_may_be_said_again() -> None:
    harness = await _round_on_umbrella(FakeCharacterModel("Yes, umbrella!"))
    await harness.container.activity.finish(RoundResult.GUESSED)
    outcome = await harness.say("Oi Mochi, is it an umbrella?")
    assert outcome.reply == "Yes, umbrella!"


# --- item 14: stale commands --------------------------------------------------------------------


async def test_old_commands_are_dropped_and_bye_is_served_once() -> None:
    harness = make_harness(character=FakeCharacterModel("[mood happy][bye] Tchau!"))
    await harness.container.sessions.start()
    await harness.say("Oi Mochi, tchau!")
    devices = harness.container.devices
    first = devices.state("home_pi_01").commands
    assert {c.kind for c in first} == {"mood", "bye"}
    assert set(json.loads(first[0].model_dump_json())) == {"command_id", "kind", "value"}
    assert [c.kind for c in devices.state("home_pi_01").commands] == ["mood"]


async def test_commands_expire_after_thirty_seconds() -> None:
    harness = make_harness(character=FakeCharacterModel("[mood happy] Oi!"))
    await harness.container.sessions.start()
    await harness.say("Oi Mochi, hi!")
    devices = harness.container.devices
    harness.clock.advance(29)
    assert [c.kind for c in devices.state("home_pi_01").commands] == ["mood"]
    harness.clock.advance(2)
    assert devices.state("home_pi_01").commands == []


# --- item 23: redaction -------------------------------------------------------------------------


async def test_agora_error_bodies_are_redacted_before_they_are_logged() -> None:
    body = '{"detail": "bad key sk-model-123 and turn-key-abc and rest-secret-xyz"}'
    http = FakeHttpClient([HttpResponse(400, body)])
    client = AgoraRestClient(http, "APPID", "rk", "rest-secret-xyz", SequentialIdGenerator())
    client.hide_secrets(("sk-model-123", "turn-key-abc", "rest-secret-xyz", ""))
    with pytest.raises(Exception) as raised:
        await client.start_agent(REQUEST)
    text = str(raised.value)
    assert "returned 400" in text and "bad key" in text
    assert not any(s in text for s in ("sk-model-123", "turn-key-abc", "rest-secret-xyz"))
