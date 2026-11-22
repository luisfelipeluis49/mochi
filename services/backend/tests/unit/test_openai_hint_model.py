"""The OpenAI-compatible hint model adapter."""

import json

import pytest

from mochi_backend.intelligence.model_port import ModelRequest, NullHintModel, Suspect
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_contracts import Language
from tests.fakes.fake_http_client import FakeHttpClient

REQUEST = ModelRequest(
    text="How do you say cancelar?", recent_texts=[], focus=Language.EN, candidate_reasons=[]
)
GOOD = json.dumps(
    {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {"decision": "SHOW_HINT", "reason": "says_unknown", "expression": "cancel"}
                    )
                }
            }
        ]
    }
)


async def test_openai_model_parses_strict_json_and_sends_the_key() -> None:
    http = FakeHttpClient([HttpResponse(200, GOOD)])
    model = OpenAiHintModel(http, "https://llm.example/v1/", "tiny", "secret-key", 2.0)
    suggestion = await model.suggest(REQUEST)
    assert suggestion is not None and suggestion.expression == "cancel"
    assert http.posts[0].url == "https://llm.example/v1/chat/completions"
    assert http.posts[0].headers["Authorization"] == "Bearer secret-key"
    assert http.posts[0].timeout_seconds == 2.0


@pytest.mark.parametrize(
    "reply",
    [
        HttpResponse(500, "boom"),
        HttpResponse(200, "not json"),
        HttpResponse(200, '{"choices": []}'),
        HttpTransportError("down"),
    ],
)
async def test_openai_model_returns_none_on_any_failure(
    reply: HttpResponse | HttpTransportError,
) -> None:
    model = OpenAiHintModel(FakeHttpClient([reply]), "https://llm.example/v1", "tiny", "k", 2.0)
    assert await model.suggest(REQUEST) is None


async def test_null_model_never_answers() -> None:
    assert await NullHintModel().suggest(REQUEST) is None


async def test_the_request_caps_how_long_an_answer_may_be() -> None:
    http = FakeHttpClient([HttpResponse(200, GOOD)])
    await OpenAiHintModel(http, "https://llm.example/v1", "tiny", "k", 2.0).suggest(REQUEST)
    assert isinstance(http.posts[0].payload, dict)
    assert http.posts[0].payload["max_completion_tokens"] == 400


async def test_a_call_that_thinks_is_not_capped() -> None:
    http = FakeHttpClient([HttpResponse(200, GOOD)])
    model = OpenAiHintModel(http, "https://llm.example/v1", "tiny", "k", 2.0).thinking("none")
    suspected = REQUEST.model_copy(
        update={"suspect": Suspect(used="fabric", meant="factory", look_alike="tecido")}
    )
    await model.suggest(suspected)
    assert isinstance(http.posts[0].payload, dict)
    assert http.posts[0].payload["reasoning_effort"] == "low"  # a suspected false friend thinks
    assert "max_completion_tokens" not in http.posts[0].payload
