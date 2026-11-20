"""What Agora and the Pi see on the wire: full OpenAI chunk shape, auth scheme, speaking window."""

import pytest
from pydantic import BaseModel

from mochi_backend.gateway.openai_sse import sse_events
from mochi_backend.gateway.routes.agora_llm import presented_key
from mochi_backend.gateway.silence_policy import SilencePolicy
from tests.fakes.fake_clock import FakeClock

CREATED = 1_700_000_000


class _ChoiceShape(BaseModel):
    index: int
    delta: dict[str, str]
    finish_reason: str | None


class _ChunkShape(BaseModel):
    id: str
    object: str
    created: int
    model: str
    choices: list[_ChoiceShape]


def _chunks(reply: str) -> list[_ChunkShape]:
    lines = [line for line in "".join(sse_events(reply, CREATED)).split("\n\n") if line]
    assert lines[-1] == "data: [DONE]"
    return [_ChunkShape.model_validate_json(line.removeprefix("data: ")) for line in lines[:-1]]


@pytest.mark.parametrize("reply", ["", "You can say: queue."])
def test_every_chunk_has_the_full_openai_shape(reply: str) -> None:
    for chunk in _chunks(reply):
        assert chunk.object == "chat.completion.chunk" and chunk.created == CREATED
        assert chunk.id and chunk.model and chunk.choices[0].index == 0


def test_an_empty_reply_is_an_empty_content_chunk_then_a_stop_chunk() -> None:
    first, last = _chunks("")
    assert first.choices[0].delta == {"role": "assistant", "content": ""}
    assert last.choices[0].delta == {} and last.choices[0].finish_reason == "stop"


def test_a_spoken_reply_carries_the_role_once_and_the_text_in_the_first_chunk() -> None:
    first, last = _chunks("hello")
    assert first.choices[0].delta == {"role": "assistant", "content": "hello"}
    assert "role" not in last.choices[0].delta


@pytest.mark.parametrize("header", ["Bearer k", "bearer k", "BEARER   k"])
def test_the_bearer_scheme_is_case_insensitive(header: str) -> None:
    assert presented_key(None, header) == "k"


def test_our_own_header_wins_over_authorization() -> None:
    assert presented_key("mine", "Bearer other") == "mine"
    assert presented_key(None, None) == ""


def test_a_short_line_does_not_shorten_a_longer_speaking_window() -> None:
    clock = FakeClock()
    policy = SilencePolicy("mute_speaker", clock, 0.6, 0.45)
    policy.begin_speaking("one two three four five six seven eight")  # 4.2 s
    policy.begin_speaking("hi")  # 1.05 s: must not replace the longer window
    clock.advance(2.0)
    assert policy.speaker_muted() is False  # Mochi is still speaking, so the mic stays open
