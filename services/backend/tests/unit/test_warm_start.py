"""The connections to the models are opened when a session starts, not by its first sentence."""

import asyncio

from mochi_backend.composition import _openai_character, _openai_hints
from mochi_backend.intelligence.openai_character_model import (
    CharacterModelConfig,
    OpenAiCharacterModel,
)
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.warm_start import WARM_CONNECTIONS, WarmsUp, open_connections
from mochi_backend.platform.http_client import HttpResponse
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.settings import load_settings
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_http_getter import FakeHttpGetter
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.warmed_models import UnreachableGetter, WarmedCharacterModel, WarmedHintModel

URL = "https://llm.example/v1"


async def test_two_connections_are_opened_without_spending_tokens() -> None:
    """Two, because a slow first request is asked a second time on a connection of its own."""
    getter = FakeHttpGetter({"/models/m": HttpResponse(200, "{}")})
    await open_connections(getter, URL + "/", "m", "secret")
    assert getter.urls == [URL + "/models/m"] * WARM_CONNECTIONS
    assert all(headers == {"Authorization": "Bearer secret"} for headers in getter.headers)


async def test_a_warm_up_that_fails_costs_nothing() -> None:
    getter = UnreachableGetter()
    await open_connections(getter, URL, "m", "k")  # does not raise
    assert len(getter.urls) == WARM_CONNECTIONS


async def test_both_adapters_warm_up_only_when_given_a_client_for_it() -> None:
    getter = FakeHttpGetter({})
    hints = OpenAiHintModel(FakeHttpClient([]), URL, "m", "k", 2.0)
    voice = OpenAiCharacterModel(FakeHttpClient([]), CharacterModelConfig(URL, "c", "k", 6.0))
    await hints.warm_up()
    await voice.warm_up()
    assert getter.urls == []
    await hints.warming(getter).warm_up()
    await voice.warming(getter).warm_up()
    assert getter.urls == [URL + "/models/m"] * 2 + [URL + "/models/c"] * 2
    assert isinstance(hints, WarmsUp) and isinstance(voice, WarmsUp)


async def test_a_session_start_warms_both_models() -> None:
    hints, voice = WarmedHintModel(), WarmedCharacterModel("[mood happy] Oi!")
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=hints)
    brain.speak_as(voice)
    brain.session_started(True)
    assert (hints.warm_ups, voice.warm_ups) == (0, 0)  # in the background: a start never waits
    await asyncio.sleep(0)
    assert (hints.warm_ups, voice.warm_ups) == (1, 1)


def test_a_session_started_outside_a_running_loop_is_left_alone() -> None:
    hints = WarmedHintModel()
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=hints)
    brain.session_started(False)  # a plain call: no loop to run the warm-up in, and no error
    assert hints.warm_ups == 0


async def test_a_model_that_cannot_warm_up_is_left_alone() -> None:
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel())
    brain.session_started(True)
    await asyncio.sleep(0)


def test_the_deployed_models_are_wired_to_warm_up() -> None:
    settings = load_settings({"MOCHI_AGORA_MODE": "fake", "MODEL_API_KEY": "k"})
    hints = _openai_hints(settings, FakeEventLogger())
    assert isinstance(hints, OpenAiHintModel) and hints._getter is not None
    assert _openai_character(settings, FakeEventLogger())._getter is not None
