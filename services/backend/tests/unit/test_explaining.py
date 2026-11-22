"""Idioms and technical terms explained to the people listening (DECISIONS D-53)."""

import asyncio
import json

from mochi_backend.intelligence.explain_port import (
    ExplainRequest,
    Explanation,
    NullExplainModel,
)
from mochi_backend.intelligence.explaining import Explainer, someone_listening_learns
from mochi_backend.intelligence.json_chat import JsonChat, JsonChatConfig
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.openai_explain_model import (
    OpenAiExplainModel,
    parse_explanation,
)
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_contracts import Language, MarkKind, SessionMode, Turn
from tests.factories import ANA, make_context, make_hint, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_explain_model import FakeExplainModel, GatedExplainModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_sender import FakeEventLogger

CIRCLE = "Let's circle back on pricing after the launch."
IDIOMS = {"circle back": "voltar ao assunto depois", "touch base": "falar rapidamente"}


def _by(turn: Turn, speaker: str | None) -> Turn:
    return turn.model_copy(update={"speaker_user_id": speaker})


def _explainer(
    model: FakeExplainModel | None = None, **tuning: bool | float | int
) -> tuple[Explainer, FakeExplainModel, FakeClock]:
    model, clock = model or FakeExplainModel(IDIOMS), FakeClock()
    settings = IntelligenceSettings(**tuning)  # type: ignore[arg-type]
    return Explainer(model, Lexicon.load(), clock, settings), model, clock


async def test_an_idiom_a_listener_is_learning_the_language_of_is_explained() -> None:
    explainer, model, _ = _explainer()
    mark = await explainer.explain(_by(make_turn(CIRCLE), "ben"), make_context())
    assert mark is not None and (mark.kind, mark.text) == (MarkKind.IDIOM, "circle back")
    assert (mark.gloss, mark.plain) == ("voltar ao assunto depois", "say it simply")
    [asked] = model.requests
    assert (asked.language, asked.explain_in) == (Language.EN, Language.PT_BR)


async def test_nobody_is_asked_when_nobody_listening_needs_it() -> None:
    explainer, model, _ = _explainer()
    assert someone_listening_learns(make_context(), Language.EN, "ben")
    assert not someone_listening_learns(make_context(), Language.EN, "ana")  # only she learns it
    assert someone_listening_learns(make_context(), Language.EN, None)  # a voice nobody knows
    assert await explainer.explain(_by(make_turn(CIRCLE), "ana"), make_context()) is None
    review = make_context(participants=[ANA], mode=SessionMode.REVIEW)
    assert await explainer.explain(make_turn(CIRCLE), review) is None
    assert await explainer.explain(make_turn("Let's circle back."), make_context()) is None
    assert model.requests == []  # a sentence of three words is not worth a call either


async def test_quiet_rules_hold_for_explanations_too() -> None:
    explainer, model, _ = _explainer()
    serious = "We will circle back after the funeral of his father."
    assert await explainer.explain(make_turn(serious), make_context()) is None
    to_mochi = "Mochi, what does circle back mean in this sentence?"
    assert await explainer.explain(make_turn(to_mochi), make_context()) is None
    assert model.requests == []
    showing = make_context(hints=[make_hint(0)])  # a hint made at 0 s lives until 8 s
    # ... and is no reason to keep quiet: the line is marked, the device keeps showing the hint
    assert await explainer.explain(make_turn(CIRCLE, 3), showing) is not None


async def test_an_expression_is_explained_once_and_not_two_in_a_row() -> None:
    explainer, model, clock = _explainer()
    assert await explainer.explain(make_turn(CIRCLE), make_context()) is not None
    clock.advance(5)
    other = "We should touch base with the design team tomorrow."
    assert await explainer.explain(make_turn(other, 5), make_context()) is None  # too soon
    clock.advance(30)
    assert await explainer.explain(make_turn(CIRCLE, 35), make_context()) is None  # known now
    assert await explainer.explain(make_turn(other, 35), make_context()) is not None
    explainer.fresh_session()
    assert await explainer.explain(make_turn(CIRCLE, 36), make_context()) is not None
    assert len(model.requests) == 4  # the too-soon one was never asked


async def test_two_answers_that_cross_give_one_explanation_and_an_old_sessions_gives_none() -> None:
    model = GatedExplainModel(IDIOMS)
    explainer, _, _ = _explainer(model)
    other = "We should touch base with the design team tomorrow."
    first = asyncio.ensure_future(explainer.explain(make_turn(CIRCLE), make_context()))
    second = asyncio.ensure_future(explainer.explain(make_turn(other, 1), make_context()))
    await asyncio.sleep(0)  # both were asked before either answer came
    model.gate.set()
    marks = [await first, await second]
    assert [m.text for m in marks if m is not None] == ["circle back"]
    model.gate.clear()
    late = asyncio.ensure_future(explainer.explain(make_turn(other, 60), make_context()))
    await asyncio.sleep(0)
    explainer.fresh_session()  # Stop and a new Start while the model was thinking
    model.gate.set()
    assert await late is None
    assert await explainer.explain(make_turn(other, 61), make_context()) is not None


def test_an_answer_that_does_not_hold_up_is_not_shown() -> None:
    explainer, _, _ = _explainer()
    good = Explanation(
        decision="EXPLAIN", kind="idiom", expression="circle back", meaning="voltar", confidence=0.9
    )
    for doubtful in (
        None,
        Explanation(decision="IGNORE"),
        good.model_copy(update={"confidence": 0.5}),
        good.model_copy(update={"confidence": None}),
        good.model_copy(update={"expression": "low-hanging fruit"}),  # not in the sentence
        good.model_copy(update={"meaning": "circle back"}),  # explains nothing
        good.model_copy(update={"meaning": ""}),
        good.model_copy(update={"kind": None}),
        good.model_copy(update={"expression": "Let's circle back on pricing after the launch"}),
    ):
        assert explainer.accepted(CIRCLE, doubtful) is None
    assert explainer.accepted(CIRCLE, good) is not None


async def test_a_model_that_fails_or_is_switched_off_costs_nothing() -> None:
    class Broken(FakeExplainModel):
        async def explain(self, request: ExplainRequest) -> Explanation | None:
            raise RuntimeError("boom")

    broken, _, _ = _explainer(Broken())
    assert await broken.explain(make_turn(CIRCLE), make_context()) is None
    off, model, _ = _explainer(explain_terms=False)
    assert await off.explain(make_turn(CIRCLE), make_context()) is None and model.requests == []
    off.use(FakeExplainModel(IDIOMS))
    assert await NullExplainModel().explain(model.requests and model.requests[0]) is None  # type: ignore[arg-type]


def _reply(content: str) -> HttpResponse:
    return HttpResponse(200, json.dumps({"choices": [{"message": {"content": content}}]}))


async def test_the_openai_explainer_asks_for_json_and_reads_it() -> None:
    answer = '{"decision": "EXPLAIN", "kind": "technical_term", "expression": "churn rate", '
    answer += '"meaning": "taxa de cancelamento", "plain": "customers who leave", "confidence": 85}'
    http = FakeHttpClient([_reply(answer), _reply("not json"), HttpResponse(500, "")])
    config = JsonChatConfig("https://llm.example/v1/", "tiny", "secret-key", 2.0, "none")
    logger = FakeEventLogger()
    model = OpenAiExplainModel(JsonChat(http, config, "explain", logger))
    request = ExplainRequest(
        text="Our churn rate went up.",
        recent_texts=[],
        language=Language.EN,
        explain_in=Language.PT_BR,
    )
    found = await model.explain(request)
    assert found is not None and found.expression == "churn rate" and found.confidence == 0.85
    post = http.posts[0]
    assert post.url == "https://llm.example/v1/chat/completions"
    assert post.headers["Authorization"] == "Bearer secret-key"
    assert isinstance(post.payload, dict) and post.payload["reasoning_effort"] == "none"
    assert "temperature" not in post.payload
    assert await model.explain(request) is None  # not the JSON that was asked for
    assert await model.explain(request) is None  # HTTP 500
    assert ("json_model_failed", {"model": "tiny", "kind": "explain", "why": "HTTP 500"}) in (
        logger.lines
    )
    await model.warm_up()  # no getter given: nothing to open, nothing raised


async def test_json_chat_survives_a_dead_connection_and_uses_temperature_without_effort() -> None:
    http = FakeHttpClient([HttpTransportError("down"), _reply("{}")])
    chat = JsonChat(http, JsonChatConfig("https://llm.example/v1", "tiny", "k", 2.0), "coach")
    assert await chat.ask([]) is None
    assert await chat.ask([]) == "{}"
    assert isinstance(http.posts[1].payload, dict) and http.posts[1].payload["temperature"] == 0


def test_explanations_are_parsed_leniently_but_never_invented() -> None:
    assert parse_explanation('{"decision": "IGNORE"}') == Explanation(decision="IGNORE")
    assert parse_explanation("[1, 2]") is None
    assert parse_explanation('{"decision": "MAYBE"}') is None
    sure = parse_explanation('{"decision": "EXPLAIN", "kind": "idiom", "confidence": "high"}')
    assert sure is not None and sure.confidence is None
