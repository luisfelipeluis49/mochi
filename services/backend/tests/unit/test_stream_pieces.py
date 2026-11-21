"""MOCHI_STREAM_REPLY parts: what may be said yet, [quiet] and [play], model SSE, our SSE."""

import json

import pytest

from mochi_backend.gateway.device_commands import split_commands
from mochi_backend.gateway.openai_sse import closing_lines, content_chunk, parse_stream
from mochi_backend.gateway.spoken_release import SpokenOutlet, SpokenRelease
from mochi_backend.intelligence.character_port import (
    CharacterRequest,
    CharacterStreamError,
    DeviceStatus,
)
from mochi_backend.intelligence.openai_character_model import (
    CharacterModelConfig,
    OpenAiCharacterModel,
)
from mochi_backend.intelligence.openai_character_stream import chunk_of, is_done
from mochi_backend.intelligence.streamed_line import streamed_line
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_line_streamer import FakeLineStreamer
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.fake_streaming_character_model import FakeStreamingCharacterModel
from tests.fakes.list_sink import ListSink

REQUEST = CharacterRequest(text="Mochi, how are you?", history=[], status=DeviceStatus())
LINE = "[mood happy] I'm great, thanks [show smile] for asking! And you, my friend?"


def _released(pieces: list[str]) -> tuple[list[str], str]:
    release = SpokenRelease()
    said = [fresh for piece in pieces if (fresh := release.feed(piece))]
    tail = release.rest(split_commands("".join(pieces))[0])
    return said, tail


def test_the_first_piece_waits_for_a_clause_end_then_words_flow() -> None:
    release = SpokenRelease()
    assert release.feed("Hi") == ""
    assert release.feed(" there,") == ""  # "there," may still grow
    assert release.feed(" how") == "Hi there,"
    assert release.feed(" are you") == " how are"
    assert release.rest("Hi there, how are you?") == " you?"


def test_six_words_without_punctuation_are_a_first_piece() -> None:
    release = SpokenRelease()
    assert release.feed("one two three four five") == ""
    assert release.feed(" six seven") == "one two three four five six"


@pytest.mark.parametrize("first", range(1, len(LINE)))
def test_any_split_says_exactly_what_split_commands_says(first: int) -> None:
    for second in (first + 3, first + 11):
        said, tail = _released([LINE[:first], LINE[first:second], LINE[second:]])
        assert "".join(said) + tail == split_commands(LINE)[0]
        assert not any("[" in piece or "mood" in piece or "smile" in piece for piece in said)


def test_a_command_split_across_tokens_is_never_said() -> None:
    said, tail = _released(["[mo", "od hap", "py] Oi, tudo", " bem? Que", " bom."])
    assert "".join(said) + tail == "Oi, tudo bem? Que bom."
    assert all("mood" not in piece and "happy" not in piece for piece in said)


async def test_quiet_split_across_tokens_says_nothing() -> None:
    outlet = SpokenOutlet(lambda: True)
    model = FakeStreamingCharacterModel("[qu", "iet]")
    assert await streamed_line(model, REQUEST, outlet) == "[quiet]"
    outlet.finish("")  # the commit says nothing for a quiet line
    assert [piece async for piece in outlet.pieces()] == []


async def test_quiet_after_words_stops_passing_on() -> None:
    sink = ListSink()
    model = FakeStreamingCharacterModel("Oh, hello", " there. [qu", "iet] more words")
    await streamed_line(model, REQUEST, sink)
    assert sink.pieces == ["Oh, hello", " there. [qu"]  # the gateway holds "[qu" back


async def test_play_holds_the_whole_line_for_the_commit() -> None:
    sink = ListSink()
    model = FakeStreamingCharacterModel("[mood excited]", "[play]", " Yay,", " let's play!")
    line = await streamed_line(model, REQUEST, sink)
    assert line == "[mood excited][play] Yay, let's play!" and sink.pieces == ["[mood excited]"]


async def test_a_broken_stream_is_no_line_and_the_model_is_closed() -> None:
    model = FakeStreamingCharacterModel("Hello there,", " friend.", " More", fail_after=2)
    assert await streamed_line(model, REQUEST, ListSink()) is None
    assert model.closed


async def test_the_outlet_stops_once_it_may_no_longer_speak() -> None:
    allowed = [True]
    outlet = SpokenOutlet(lambda: allowed[0])
    outlet.put("Hello there, ")
    allowed[0] = False  # a Stop, a Reset or a round
    outlet.put("my friend, ")
    allowed[0] = True  # silenced for good
    outlet.put("again. ")
    outlet.finish("")
    assert [piece async for piece in outlet.pieces()] == ["Hello there,"]
    assert outlet.spoken()


def _sse(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]})


USAGE_LINE = "data: " + json.dumps(
    {"choices": [], "usage": {"prompt_tokens": 800, "completion_tokens": 9}}
)


async def test_the_openai_model_streams_deltas_and_logs_usage() -> None:
    lines: list[str | HttpTransportError] = [
        _sse("Hi"),
        "",
        _sse(" there!"),
        USAGE_LINE,
        "data: [DONE]",
    ]
    streamer, logger = FakeLineStreamer(lines), FakeEventLogger()
    config = CharacterModelConfig("https://x/v1", "char-m", "secret-key", 6.0)
    model = OpenAiCharacterModel(FakeHttpClient([]), config, logger).streaming(streamer)
    assert [piece async for piece in model.stream_reply(REQUEST)] == ["Hi", " there!"]
    payload = streamer.posts[0].payload
    assert isinstance(payload, dict) and payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert [e for e, _ in logger.lines] == ["model_usage"]


@pytest.mark.parametrize(
    "lines",
    [
        [_sse("Hi")],  # cut off: no [DONE]
        [_sse("Hi"), HttpTransportError("reset by peer")],
        ["data: not json", "data: [DONE]"],
    ],
)
async def test_a_broken_model_stream_is_logged_and_raised(
    lines: list[str | HttpTransportError],
) -> None:
    logger = FakeEventLogger()
    config = CharacterModelConfig("https://x/v1", "char-m", "k", 6.0)
    model = OpenAiCharacterModel(FakeHttpClient([]), config, logger).streaming(
        FakeLineStreamer(lines)
    )
    with pytest.raises(CharacterStreamError):
        _ = [piece async for piece in model.stream_reply(REQUEST)]
    assert [e for e, _ in logger.lines] == ["character_model_failed"]


async def test_without_a_streamer_the_whole_reply_is_one_piece() -> None:
    reply = HttpResponse(200, json.dumps({"choices": [{"message": {"content": "Oi!"}}]}))
    config = CharacterModelConfig("https://x/v1", "char-m", "k", 6.0)
    model = OpenAiCharacterModel(FakeHttpClient([reply]), config)
    assert [piece async for piece in model.stream_reply(REQUEST)] == ["Oi!"]
    failing = OpenAiCharacterModel(FakeHttpClient([HttpResponse(500, "")]), config)
    with pytest.raises(CharacterStreamError):
        _ = [piece async for piece in failing.stream_reply(REQUEST)]


def test_chunk_parsing_skips_blank_and_done_lines() -> None:
    assert chunk_of("") is None and chunk_of(": keep-alive") is None
    assert chunk_of("data: [DONE]") is None and is_done("data: [DONE]")
    parsed = chunk_of(_sse("Hi"))
    assert parsed is not None and parsed.text == "Hi"


def test_our_sse_has_several_deltas_then_stop_then_done() -> None:
    raw = content_chunk("Hi, ", 7, first=True) + content_chunk("there!", 7, first=False)
    raw += "".join(closing_lines(7))
    text, done = parse_stream(raw)
    assert text == "Hi, there!" and done and raw.endswith("data: [DONE]\n\n")
    first = json.loads(raw.split("\n\n")[0].removeprefix("data: "))
    second = json.loads(raw.split("\n\n")[1].removeprefix("data: "))
    assert first["choices"][0]["delta"]["role"] == "assistant"
    assert "role" not in second["choices"][0]["delta"]
    stop = json.loads(raw.split("\n\n")[2].removeprefix("data: "))
    assert (
        stop["choices"][0]["finish_reason"] == "stop" and first["object"] == "chat.completion.chunk"
    )
