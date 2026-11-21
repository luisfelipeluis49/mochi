"""`model_usage`: one metadata-only line per model call that answered (DECISIONS D-37)."""

import json
from collections.abc import Mapping

from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus
from mochi_backend.intelligence.model_port import ModelRequest
from mochi_backend.intelligence.model_usage import ModelUsage, log_usage
from mochi_backend.intelligence.openai_character_model import (
    CharacterModelConfig,
    OpenAiCharacterModel,
)
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.platform.http_client import HttpResponse
from mochi_contracts import Language
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_sender import FakeEventLogger

USAGE = {
    "prompt_tokens": 1200,
    "completion_tokens": 18,
    "prompt_tokens_details": {"cached_tokens": 1024},
}
HINT_JSON = json.dumps({"decision": "IGNORE"})
SENTENCE = "I need to adiar my meeting"


def _usage_lines(logger: FakeEventLogger) -> list[dict[str, object]]:
    return [dict(fields) for event, fields in logger.lines if event == "model_usage"]


def _reply(content: str, usage: Mapping[str, object] | None) -> HttpResponse:
    body: dict[str, object] = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return HttpResponse(200, json.dumps(body))


async def test_the_hint_model_logs_its_tokens_and_never_the_sentence() -> None:
    logger = FakeEventLogger()
    http = FakeHttpClient([_reply(HINT_JSON, USAGE)])
    model = OpenAiHintModel(http, "https://x/v1", "hint-m", "secret-key", 2.0).logging(logger)
    await model.suggest(
        ModelRequest(text=SENTENCE, focus=Language.EN, recent_texts=[], candidate_reasons=[])
    )
    [line] = _usage_lines(logger)
    assert line["model"] == "hint-m" and line["kind"] == "hint"
    assert (line["prompt_tokens"], line["completion_tokens"], line["cached_tokens"]) == (
        1200,
        18,
        1024,
    )
    assert isinstance(line["latency_ms"], float)
    assert "adiar" not in json.dumps(logger.lines) and "secret-key" not in json.dumps(logger.lines)


async def test_the_character_model_logs_usage_with_zero_cached_when_absent() -> None:
    logger = FakeEventLogger()
    usage = {"prompt_tokens": 900, "completion_tokens": 12}
    http = FakeHttpClient([_reply("[mood happy] Oi!", usage)])
    config = CharacterModelConfig("https://x/v1", "char-m", "k", 6.0)
    request = CharacterRequest(text="Hi Mochi!", history=[], status=DeviceStatus())
    assert await OpenAiCharacterModel(http, config, logger).reply(request) == "[mood happy] Oi!"
    [line] = _usage_lines(logger)
    assert line["kind"] == "character" and line["model"] == "char-m"
    assert line["cached_tokens"] == 0 and line["prompt_tokens"] == 900


async def test_a_reply_without_usage_logs_nothing_and_still_answers() -> None:
    logger = FakeEventLogger()
    http = FakeHttpClient([_reply(HINT_JSON, None)])
    model = OpenAiHintModel(http, "https://x/v1", "m", "k", 2.0).logging(logger)
    await model.suggest(
        ModelRequest(text="Hello there", focus=Language.EN, recent_texts=[], candidate_reasons=[])
    )
    assert _usage_lines(logger) == []


def test_log_usage_without_a_logger_is_a_no_op() -> None:
    log_usage(None, "m", "hint", ModelUsage(prompt_tokens=1), 0.0)
