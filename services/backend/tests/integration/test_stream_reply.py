"""MOCHI_STREAM_REPLY end to end: a free-chat line reaches Agora in pieces, nothing else does."""

import json

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.composition import _openai_character, _streamer
from mochi_backend.gateway.openai_sse import parse_stream
from mochi_backend.intelligence.character_port import CharacterModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.settings import load_settings
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.fake_streaming_character_model import FakeStreamingCharacterModel
from tests.harness import HOME, Harness, make_harness

URL = "/agora/llm/demo/chat/completions"
KEY = {"x-mochi-key": "k"}
ON = {"MOCHI_STREAM_REPLY": "true", "MOCHI_ENABLE_DEV_ROUTES": "true"}
OFF = {"MOCHI_ENABLE_DEV_ROUTES": "true"}
CHAT = "Hi Mochi, how was your day?"
PIECES = ("[mood happy] I'm", " great,", " thanks", " for asking!", " And", " you?")
SAID = "I'm great, thanks for asking! And you?"


def _client(env: dict[str, str], character: CharacterModel) -> tuple[Harness, TestClient]:
    harness = make_harness(env=env, character=character)
    client = TestClient(create_app(harness.container))
    assert client.post("/api/sessions/demo/start").status_code == 200
    return harness, client


def _turn(client: TestClient, text: str, stream: bool = True) -> str:
    body = {"messages": [{"role": "user", "content": text}], "stream": stream}
    reply = client.post(URL, json=body, headers=KEY)
    assert reply.status_code == 200
    return str(reply.text)


def _contents(raw: str) -> list[str]:
    payloads = [line.removeprefix("data: ") for line in raw.split("\n\n") if line]
    chunks = [json.loads(p) for p in payloads if p != "[DONE]"]
    return [
        c["choices"][0]["delta"]["content"] for c in chunks if "content" in c["choices"][0]["delta"]
    ]


def test_a_free_chat_line_streams_in_several_deltas_then_stop_and_done() -> None:
    model = FakeStreamingCharacterModel(*PIECES)
    harness, client = _client(ON, model)
    raw = _turn(client, CHAT)
    text, done = parse_stream(raw)
    assert text == SAID and done and len(_contents(raw)) > 1
    assert model.streamed == 1 and model.replied == 0
    assert raw.endswith('"finish_reason": "stop"}]}\n\ndata: [DONE]\n\n')
    firsts = [f for e, f in harness.logger.lines if e == "reply_first_byte"]
    assert len(firsts) == 1 and firsts[0]["segment_id"] is not None
    kinds = [c.kind for c in harness.container.devices.state("home_pi_01").commands]
    assert "mood" in kinds  # the command still reaches the device, never the voice
    [reply_line] = [f for e, f in harness.logger.lines if e == "reply"]
    assert reply_line["text"] == SAID


async def test_the_commit_still_publishes_what_was_said() -> None:
    harness = make_harness(env=ON, character=FakeStreamingCharacterModel(*PIECES))
    await harness.container.sessions.start()
    home = await harness.connect(HOME)
    outcome = await harness.container.pipeline.handle_heard(CHAT, 0, stream=True)
    assert outcome.spoken is not None
    said = "".join([piece async for piece in outcome.spoken.pieces()])
    assert said == SAID and "agent.speak.requested" in home.types()


def test_flag_off_gives_the_same_words_in_one_chunk() -> None:
    _, on = _client(ON, FakeStreamingCharacterModel(*PIECES))
    _, off = _client(OFF, FakeStreamingCharacterModel(*PIECES))
    streamed, whole = _turn(on, CHAT), _turn(off, CHAT)
    assert parse_stream(streamed)[0] == parse_stream(whole)[0] == SAID
    assert _contents(whole) == [SAID]


def test_without_the_flag_the_wire_is_byte_for_byte_todays() -> None:
    _, plain = _client(OFF, FakeCharacterModel("".join(PIECES)))
    _, streaming_model = _client(OFF, FakeStreamingCharacterModel(*PIECES))
    assert _turn(plain, CHAT) == _turn(streaming_model, CHAT)


def test_the_dev_route_gives_the_same_reply_with_the_flag_on_or_off() -> None:
    _, on = _client(ON, FakeStreamingCharacterModel(*PIECES))
    _, off = _client(OFF, FakeStreamingCharacterModel(*PIECES))
    body = {"text": CHAT}
    with_flag = on.post("/dev/sessions/demo/turn", json=body).json()
    without = off.post("/dev/sessions/demo/turn", json=body).json()
    assert with_flag["reply"] == without["reply"] == SAID
    assert with_flag["decision"]["decision"] == without["decision"]["decision"] == "SPEAK"


def test_a_request_that_does_not_stream_is_answered_as_today() -> None:
    _, client = _client(ON, FakeStreamingCharacterModel(*PIECES))
    body = {"messages": [{"role": "user", "content": CHAT}], "stream": False}
    reply = client.post(URL, json=body, headers=KEY).json()
    assert reply["choices"][0]["message"]["content"] == SAID


def test_a_hint_turn_with_the_flag_on_is_one_empty_chunk_as_today() -> None:
    _, client = _client(ON, FakeStreamingCharacterModel(*PIECES))
    raw = _turn(client, "I need to adiar my meeting tomorrow")
    assert _contents(raw) == [""] and parse_stream(raw) == ("", True)


def test_a_break_mid_stream_ends_with_stop_and_done_and_no_other_line() -> None:
    model = FakeStreamingCharacterModel("Hello there,", " my friend.", " How", fail_after=2)
    harness, client = _client(ON, model)
    raw = _turn(client, CHAT)
    assert _contents(raw) == ["Hello there, my"]  # the words complete before the break
    assert raw.endswith("data: [DONE]\n\n")
    assert all(e != "reply" for e, _ in harness.logger.lines)  # nothing remembered as said


def test_quiet_mid_stream_says_only_what_came_before() -> None:
    model = FakeStreamingCharacterModel("Oh, hello", " there. [qu", "iet] and more.")
    _, client = _client(ON, model)
    assert parse_stream(_turn(client, CHAT))[0] == "Oh, hello there."


def test_with_the_mute_speaker_strategy_the_flag_does_nothing() -> None:
    muted = {**ON, "MOCHI_SILENCE_STRATEGY": "mute_speaker"}
    model = FakeStreamingCharacterModel(*PIECES)
    harness, client = _client(muted, model)
    assert not harness.container.settings.streams_reply
    assert _contents(_turn(client, CHAT)) == [SAID] and model.streamed == 0


def test_production_wiring_turns_streaming_on_only_with_the_flag() -> None:
    """The harness builds its own brain: check the composition root's choices directly."""
    base = {"MOCHI_AGORA_MODE": "fake", "MODEL_API_KEY": "k"}
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel())
    flagged = load_settings({**base, "MOCHI_STREAM_REPLY": "true"})
    assert _streamer(flagged, brain) is brain
    assert _streamer(load_settings(base), brain) is None
    muted = load_settings(
        {**base, "MOCHI_STREAM_REPLY": "true", "MOCHI_SILENCE_STRATEGY": "mute_speaker"}
    )
    assert _streamer(muted, brain) is None
    assert _openai_character(flagged, FakeEventLogger())._lines is not None
    assert _openai_character(load_settings(base), FakeEventLogger())._lines is None
