"""MOCHI_CHARACTER_HEDGE_SECONDS: a stalled reply request gets a second one; first answer wins."""

import json

from mochi_backend.composition import _character_model
from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus
from mochi_backend.intelligence.openai_character_model import (
    CharacterModelConfig,
    OpenAiCharacterModel,
)
from mochi_backend.platform.http_client import HttpResponse
from mochi_backend.settings import load_settings
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.stalled_http_client import StalledFirstHttpClient

REQUEST = CharacterRequest(text="Hi Mochi!", history=[], status=DeviceStatus())
GOOD = HttpResponse(200, json.dumps({"choices": [{"message": {"content": "Oi!"}}]}))


def _config(hedge: float) -> CharacterModelConfig:
    return CharacterModelConfig("https://x/v1", "char-m", "k", 6.0, hedge_after_seconds=hedge)


async def test_a_stalled_request_is_hedged_and_the_second_answer_wins() -> None:
    http = StalledFirstHttpClient(GOOD)
    logger = FakeEventLogger()
    # a near-zero hedge: the second request starts at once (no timed wait in the test)
    model = OpenAiCharacterModel(http, _config(1e-9), logger)
    assert await model.reply(REQUEST) == "Oi!"
    assert http.calls == 2 and http.stalled_cancelled
    assert [event for event, _ in logger.lines if event == "character_hedge_used"] == [
        "character_hedge_used"
    ]


async def test_hedge_off_sends_exactly_one_request_like_today() -> None:
    http = FakeHttpClient([GOOD])
    logger = FakeEventLogger()
    assert await OpenAiCharacterModel(http, _config(0.0), logger).reply(REQUEST) == "Oi!"
    assert len(http.posts) == 1
    assert all(event != "character_hedge_used" for event, _ in logger.lines)


async def test_a_fast_answer_never_starts_the_hedge() -> None:
    http = FakeHttpClient([GOOD])
    logger = FakeEventLogger()
    assert await OpenAiCharacterModel(http, _config(5.0), logger).reply(REQUEST) == "Oi!"
    assert len(http.posts) == 1 and all(e != "character_hedge_used" for e, _ in logger.lines)


def test_the_setting_defaults_to_off_and_reaches_the_config() -> None:
    assert load_settings({"MOCHI_AGORA_MODE": "fake"}).mochi_character_hedge_seconds == 0.0
    tuned = load_settings({"MOCHI_AGORA_MODE": "fake", "MOCHI_CHARACTER_HEDGE_SECONDS": "1.5"})
    assert _character_model(tuned).hedge_after_seconds == 1.5
