"""Mochi's body: commands for the device ride on its state, and the device reports back."""

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.client_port import AgentStartRequest, SpeechTuning
from mochi_backend.gateway.agora.rest_client import join_body
from mochi_backend.gateway.device_commands import split_commands
from mochi_backend.settings import load_settings
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.harness import HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
ASK_WORD = "Oi Mochi, what's the word for fila?"
ASK_LOUDER = "Hi Mochi, can you speak a bit louder?"
STATE = "/api/devices/home_pi_01/state"


def _client(*lines: str | None) -> tuple[TestClient, Harness]:
    harness = make_harness(character=FakeCharacterModel(*lines) if lines else None)
    return TestClient(create_app(harness.container)), harness


def _commands(client: TestClient) -> list[tuple[str, str]]:
    return [(c["kind"], c["value"]) for c in client.get(STATE).json()["commands"]]


def test_brackets_are_never_spoken_and_other_brackets_are_dropped() -> None:
    text, written = split_commands("[mood cool][Volume: 80] Louder it is! [wink]")
    assert text == "Louder it is!" and written == [("mood", "cool"), ("volume", "80")]
    assert split_commands("[mood sleepy][temp]") == ("", [("mood", "sleepy"), ("temp", "")])
    assert split_commands("You can say: queue.") == ("You can say: queue.", [])
    said, written = split_commands("[mood happy][bye] Tchau tchau! Até a próxima.")
    assert said == "Tchau tchau! Até a próxima." and written == [("mood", "happy"), ("bye", "")]


async def test_what_mochi_wrote_in_brackets_goes_to_the_device_not_to_the_speaker() -> None:
    harness = make_harness(character=FakeCharacterModel("[mood cool][volume 80] Louder it is!"))
    await harness.container.sessions.start()
    home = await harness.connect(HOME)
    outcome = await harness.say(ASK_LOUDER)
    assert outcome.reply == "Louder it is!"
    spoken = [e.payload for e in home.events if e.type.value == "agent.speak.requested"]
    assert [getattr(s, "text", None) for s in spoken] == ["Louder it is!"]
    commands = harness.container.devices.state("home_pi_01").commands
    assert [(c.kind, c.value) for c in commands] == [("mood", "cool"), ("volume", "80")]
    assert len({c.command_id for c in commands}) == 2


async def test_a_reply_of_only_commands_says_nothing() -> None:
    harness = make_harness(character=FakeCharacterModel("[mood sleepy][temp]"))
    await harness.container.sessions.start()
    home = await harness.connect(HOME)
    outcome = await harness.say("Hi Mochi, how hot are you?")
    assert outcome.reply == "" and "agent.speak.requested" not in home.types()
    assert len(harness.container.core.store.commands) == 2


async def test_a_quiet_hint_shows_its_word_and_mochis_own_show_is_not_doubled() -> None:
    quiet = make_harness()
    await quiet.container.sessions.start()
    await quiet.say(ADIAR)
    assert [(c.kind, c.value) for c in quiet.container.core.store.commands] == [
        ("show", "postpone")
    ]
    talking = make_harness(character=FakeCharacterModel("[mood excited][show queue] Queue!"))
    await talking.container.sessions.start()
    await talking.say(ASK_WORD)
    kinds = [(c.kind, c.value) for c in talking.container.core.store.commands]
    assert kinds == [("mood", "excited"), ("show", "queue")]


async def test_commands_belong_to_one_session() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.say(ADIAR)
    await harness.container.sessions.stop()
    assert harness.container.core.store.commands == []
    await harness.container.sessions.start()
    assert harness.container.devices.state("home_pi_01").commands == []


def test_the_device_reports_itself_and_mochi_knows() -> None:
    mochi = FakeCharacterModel("[mood sleepy][temp] Fifty-two degrees.")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    report = {"volume": 80, "temperature": 52.4, "voices": ["Ana"], "speaker": "Ana"}
    assert client.post("/api/devices/home_pi_01/status", json=report).status_code == 204
    assert client.post("/api/devices/pi_99/status", json=report).status_code == 404
    client.post("/api/sessions/demo/start")
    client.post("/dev/sessions/demo/turn", json={"text": "Hi Mochi, how hot are you?"})
    status = mochi.requests[0].status
    assert (status.volume, status.temperature, status.voices, status.speaker) == (
        80,
        52,
        ["Ana"],
        "Ana",
    )
    assert _commands(client) == [("mood", "sleepy"), ("temp", "")]


def test_a_learned_voice_is_confirmed_out_loud_in_its_language() -> None:
    client, harness = _client()
    client.post("/api/sessions/demo/start")
    learned = {"name": "Ana", "language": "pt", "learned": True}
    assert client.post("/api/devices/home_pi_01/voices", json=learned).status_code == 204
    failed = {"name": "Ben", "language": "en", "learned": False}
    assert client.post("/api/devices/home_pi_01/voices", json=failed).status_code == 204
    lines = [text for _agent, text in harness.agora.spoken]
    assert lines[0] == "Pronto, Ana! Agora eu conheço a sua voz."
    assert lines[1].startswith("Sorry, Ben, I didn't hear enough.")
    assert client.post("/api/devices/pi_99/voices", json=learned).status_code == 404


def test_woken_by_its_wake_phrase_mochi_greets_in_that_language_and_listens() -> None:
    mochi = FakeCharacterModel("[mood happy] Tudo ótimo!")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start", json={"woken_by": "oi mochi"})
    assert harness.agora.started[0].greeting == "Oi! Pode falar."
    reply = client.post("/dev/sessions/demo/turn", json={"text": "Tudo bem com você?"}).json()
    assert reply["reply"] == "Tudo ótimo!" and mochi.requests[0].named is False
    assert mochi.requests[0].woken is True and mochi.requests[0].language.value == "pt-BR"
    client.post("/api/sessions/demo/stop")
    client.post("/api/sessions/demo/start", json={"woken_by": "hey mochi"})
    assert harness.agora.started[1].greeting == "Hi! I'm listening."


def test_started_by_the_operator_mochi_says_nothing_and_waits_for_its_name() -> None:
    mochi = FakeCharacterModel("[mood happy] Hello!")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    assert harness.agora.started[0].greeting == ""
    reply = client.post("/dev/sessions/demo/turn", json={"text": "How was your day?"}).json()
    assert reply["reply"] == "" and mochi.requests == []


def test_the_greeting_is_sent_to_agora_only_when_there_is_one() -> None:
    quiet = AgentStartRequest("chan", 1002, 1001, "tok", "https://x/y", "k", SpeechTuning())
    body = join_body(quiet, "mochi_001")
    assert isinstance(body, dict) and isinstance(body["properties"], dict)
    llm = body["properties"]["llm"]
    assert isinstance(llm, dict) and "greeting_message" not in llm
    greeting = AgentStartRequest(
        "chan", 1002, 1001, "tok", "https://x/y", "k", SpeechTuning(), greeting="Oi! Pode falar."
    )
    body = join_body(greeting, "mochi_001")
    assert isinstance(body, dict) and isinstance(body["properties"], dict)
    llm = body["properties"]["llm"]
    assert isinstance(llm, dict) and llm["greeting_message"] == "Oi! Pode falar."


def test_mochi_writes_its_own_lines_only_with_a_model_key_and_gets_more_time() -> None:
    plain = load_settings({"MOCHI_AGORA_MODE": "fake"})
    assert plain.character_configured is False and plain.turn_timeout_seconds == 2.0
    keyed = load_settings({"MOCHI_AGORA_MODE": "fake", "MODEL_API_KEY": "k"})
    assert keyed.character_configured is True and keyed.turn_timeout_seconds == 8.0
    off = load_settings(
        {"MOCHI_AGORA_MODE": "fake", "MODEL_API_KEY": "k", "MOCHI_CHARACTER_ENABLED": "false"}
    )
    assert off.character_configured is False
