"""Mochi's body: commands for the device ride on its state, and the device reports back."""

import json

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.agora.client_port import AgentStartRequest, AgoraError, SpeechTuning
from mochi_backend.gateway.agora.rest_client import join_body
from mochi_backend.gateway.device_commands import split_commands
from mochi_backend.gateway.turn_pipeline import hint_card
from mochi_backend.settings import DEV_DEVICE_KEY, load_settings
from mochi_contracts import HintCandidate
from tests.factories import make_hint
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.harness import HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
ASK_WORD = "Oi Mochi, what's the word for fila?"
ASK_LOUDER = "Hi Mochi, can you speak a bit louder?"
STATE = "/api/devices/home_pi_01/state"
KEY = {"Authorization": f"Bearer {DEV_DEVICE_KEY}"}


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
    listen = split_commands("[mood happy][listen] Okay, I'll just listen.")
    assert listen == ("Okay, I'll just listen.", [("mood", "happy")])  # not for the device
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


async def test_a_hint_reaches_the_device_as_a_card_with_its_language_and_meaning() -> None:
    """A bare word on the screen tells too little: whose language is it, and what does it mean?"""
    quiet = make_harness()
    await quiet.container.sessions.start()
    await quiet.say(ADIAR)
    [command] = quiet.container.core.store.commands
    assert command.kind == "hint"
    assert json.loads(command.value) == {
        "word": "postpone",
        "language": "en",
        "meaning": "adiar",
        "example": "I need to postpone my meeting.",
        "why": "code_switch",  # the face draws a code switch as "adiar -> postpone" (D-52)
    }


def test_a_hint_with_other_words_that_fit_carries_them_to_the_device() -> None:
    """Someone who stopped at "I forgot my" named no word: Mochi's own screen showed only the
    first guess, the glasses all of them (D-42). A hint with one word is the card it always was."""
    words = [HintCandidate(expression=word, meaning=None) for word in ("umbrella", "raincoat")]
    open_search = make_hint(0).model_copy(update={"expression": "umbrella", "candidates": words})
    assert json.loads(hint_card(open_search))["candidates"] == ["raincoat"]  # not the word again
    assert "candidates" not in json.loads(hint_card(make_hint(0)))


async def test_saying_the_word_they_were_given_makes_the_face_cheer() -> None:
    """ "Used with help" is the moment the word starts to stick: show it, without a sound."""
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.say(ADIAR)
    await harness.say("Ok, let's postpone it then.")
    hint, used = harness.container.core.store.commands
    assert (hint.kind, used.kind) == ("hint", "used")
    assert json.loads(used.value) == {"word": "postpone", "language": "en"}


async def test_a_word_from_an_earlier_session_is_not_cheered() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.say(ADIAR)
    await harness.container.sessions.stop()
    await harness.container.sessions.start()
    await harness.say("Did they postpone the game?")
    assert [c.kind for c in harness.container.core.store.commands] == []


async def test_the_card_replaces_a_bare_word_mochi_wrote_for_the_same_turn() -> None:
    talking = make_harness(character=FakeCharacterModel("[mood excited][show queue] Queue!"))
    await talking.container.sessions.start()
    await talking.say(ASK_WORD)
    commands = talking.container.core.store.commands
    assert [c.kind for c in commands] == ["mood", "hint"]
    assert json.loads(commands[1].value)["word"] == "queue"
    assert json.loads(commands[1].value)["meaning"] == "fila"


async def test_the_hint_is_written_to_the_log() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.say(ADIAR)
    [decision] = [fields for name, fields in harness.logger.lines if name == "decision"]
    assert (decision["hint"], decision["meaning"]) == ("postpone", "adiar")


async def test_a_new_session_starts_without_the_last_ones_sentences_and_hints() -> None:
    """Seen live: the first stuck word of a session got nothing, "cooled down" by an old hint."""
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.say(ADIAR)
    await harness.container.sessions.stop()
    await harness.container.sessions.start()
    assert harness.container.core.store.turns == [] and harness.container.core.store.hints == []
    again = await harness.say("I forgot my guarda-chuva at the office.")
    assert again.decision.hint is not None and again.decision.hint.expression == "umbrella"


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
    assert (
        client.post("/api/devices/home_pi_01/status", json=report, headers=KEY).status_code == 204
    )
    assert client.post("/api/devices/pi_99/status", json=report, headers=KEY).status_code == 404
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
    assert (
        client.post("/api/devices/home_pi_01/voices", json=learned, headers=KEY).status_code == 204
    )
    failed = {"name": "Ben", "language": "en", "learned": False}
    assert (
        client.post("/api/devices/home_pi_01/voices", json=failed, headers=KEY).status_code == 204
    )
    lines = [text for _agent, text in harness.agora.spoken]
    assert lines[0] == "Pronto, Ana! Agora eu conheço a sua voz."
    assert lines[1].startswith("Sorry, Ben, I didn't hear enough.")
    assert client.post("/api/devices/pi_99/voices", json=learned, headers=KEY).status_code == 404


def test_woken_by_its_wake_phrase_mochi_greets_in_that_language_and_the_meeting_begins() -> None:
    mochi = FakeCharacterModel("[mood happy] A gente fala fila.")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start", json={"woken_by": "oi mochi"})
    assert harness.agora.started[0].greeting.startswith("Oi! Estou ouvindo.")
    # people talk to each other: a sentence without its name is not for Mochi
    overheard = client.post("/dev/sessions/demo/turn", json={"text": "Tudo bem com você?"}).json()
    assert overheard["reply"] == "" and mochi.requests == []
    asked = client.post("/dev/sessions/demo/turn", json={"text": "Mochi, você está aí?"}).json()
    assert asked["reply"] == "A gente fala fila." and mochi.requests[0].conversing is False
    assert mochi.requests[0].reviewing is False and mochi.requests[0].language.value == "pt-BR"
    client.post("/api/sessions/demo/stop")
    client.post("/api/sessions/demo/start", json={"woken_by": "hey mochi"})
    assert harness.agora.started[1].greeting.startswith("Hi! I'm listening.")


def test_a_phrase_without_the_name_is_greeted_in_its_own_language() -> None:
    # not the shipped wake phrases since D-65, but a device may still be configured with them
    harness = make_harness()
    client = TestClient(create_app(harness.container))
    for phrase, opening in (
        ("vamos papear", "Oi! Estou ouvindo."),
        ("let s chat", "Hi! I'm listening."),
    ):
        client.post("/api/sessions/demo/start", json={"woken_by": phrase})
        assert harness.agora.started[-1].greeting.startswith(opening), phrase
        client.post("/api/sessions/demo/stop")


def test_in_a_review_mochi_greets_its_person_and_every_sentence_is_for_it() -> None:
    mochi = FakeCharacterModel("[mood curious] Qual foi a palavra para adiar?")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    client.post("/dev/sessions/demo/turn", json={"text": "I need to adiar my meeting tomorrow."})
    client.post("/api/sessions/demo/stop")
    review = {"mode": "review", "user_id": "ana"}
    assert client.post("/api/sessions/p-ana/start", json=review).status_code == 200
    assert (
        harness.agora.started[-1].greeting
        == "Oi! Vamos fazer um treino rápido? Eu começo uma cena, é só responder."
    )
    reply = client.post("/dev/sessions/p-ana/turn", json={"text": "Tudo bem, vamos lá."}).json()
    assert reply["reply"] == "Qual foi a palavra para adiar?"
    request = mochi.requests[-1]
    assert request.conversing and request.reviewing and request.named is True
    assert [(w.expression, w.meaning) for w in request.review] == [("postpone", "adiar")]


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


def test_mochi_can_be_told_to_finish_its_answer_before_the_next_sentence() -> None:
    """Agora drops the answer under way when a sentence follows; "append" queues it instead."""
    plain = AgentStartRequest("chan", 1002, 1001, "tok", "https://x/y", "k", SpeechTuning())
    body = join_body(plain, "n")
    assert isinstance(body, dict) and isinstance(body["properties"], dict)
    assert "interruption" not in body["properties"]  # unset: Agora's default, as before
    queued = AgentStartRequest(
        "chan", 1002, 1001, "tok", "https://x/y", "k", SpeechTuning(interruption="append")
    )
    body = join_body(queued, "n")
    assert isinstance(body, dict) and isinstance(body["properties"], dict)
    expected = {"enable": False, "disabled_config": {"strategy": "append"}}
    assert body["properties"]["interruption"] == expected


def test_someone_talking_over_mochi_stops_it_and_it_goes_back_to_listening() -> None:
    mochi = FakeCharacterModel("[mood happy] In English we say queue.", "[mood happy] Sure!")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    assert client.post("/api/sessions/demo/interrupt").json() == {
        "interrupted": False
    }  # nothing runs
    client.post("/api/sessions/demo/start")
    asked = client.post(
        "/dev/sessions/demo/turn", json={"text": "Oi Mochi, what's the word for fila?"}
    ).json()
    assert asked["reply"].startswith("In English we say")
    assert client.post("/api/sessions/demo/interrupt").json() == {"interrupted": True}
    assert harness.agora.interrupted == ["agent-1"]
    # what the person says next is said to the room, not an answer to Mochi: it stays quiet
    after = client.post("/dev/sessions/demo/turn", json={"text": "Anyway, as I was saying."}).json()
    assert after["reply"] == "" and len(mochi.requests) == 1
    assert client.post("/api/sessions/nobody/interrupt").json() == {"interrupted": False}


def test_without_the_interruption_the_next_sentence_may_still_be_for_mochi() -> None:
    """The control for the test above: Mochi listens for an answer for a while after it spoke."""
    mochi = FakeCharacterModel("[mood happy] In English we say queue.", "[mood happy] Sure!")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    client.post("/dev/sessions/demo/turn", json={"text": "Oi Mochi, what's the word for fila?"})
    after = client.post("/dev/sessions/demo/turn", json={"text": "Anyway, as I was saying."}).json()
    assert after["reply"] == "Sure!" and len(mochi.requests) == 2


def test_in_a_review_an_interruption_stops_mochi_and_it_still_answers_its_person() -> None:
    mochi = FakeCharacterModel("[mood curious] Qual era a palavra?", "[mood happy] Isso!")
    harness = make_harness(character=mochi, env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/p-ana/start", json={"mode": "review", "user_id": "ana"})
    client.post("/dev/sessions/p-ana/turn", json={"text": "Vamos lá."})
    assert client.post("/api/sessions/p-ana/interrupt").json() == {"interrupted": True}
    again = client.post("/dev/sessions/p-ana/turn", json={"text": "Espera, eu sei essa."}).json()
    assert again["reply"] == "Isso!"


def test_an_interruption_agora_refuses_still_makes_mochi_go_quiet() -> None:
    harness = make_harness()
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    harness.agora.interrupt_error = AgoraError("POST .../interrupt returned 500")
    assert client.post("/api/sessions/demo/interrupt").json() == {"interrupted": False}
    assert "agora_interrupt_failed" in harness.logger.names()
