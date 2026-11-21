"""Fixes from the post-merge review: language of an asked word, aloud, hint latency, doubt, log."""

import asyncio
import json

import pytest

from mochi_backend.intelligence.aloud import wants_to_hear
from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, DecisionKind, Language, Reason
from tests.factories import make_context, make_turn
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.gated_character_model import GatedCharacterModel

PINEAPPLE = ModelSuggestion.model_validate(
    {
        "decision": "SHOW_HINT",
        "reason": "says_unknown",
        "expression": "pineapple",
        "meaning": "abacaxi",
        "expression_language": "en",
        "meaning_language": "pt-BR",
        "confidence": 0.95,
    }
)
GARFO = "Can you pass me the garfo, please?"
FORK = ModelSuggestion.model_validate(
    {
        "decision": "SHOW_HINT",
        "reason": "code_switch",
        "expression": "fork",
        "meaning": "garfo",
        "expression_language": "en",
        "meaning_language": "pt-BR",
        "confidence": 0.95,
    }
)


def _brain(
    model: ModelSuggestion | None, settings: IntelligenceSettings | None = None
) -> Intelligence:
    return Intelligence(
        clock=FakeClock(),
        ids=SequentialIdGenerator(),
        model=FakeHintModel(model),
        settings=settings,
    )


# ---- 5: the language the model found survives "Oi Mochi" ----


async def test_a_word_asked_in_portuguese_is_shown_in_english_for_the_english_learner() -> None:
    brain = _brain(PINEAPPLE)
    decision = await brain.decide(make_turn("Oi Mochi, como se diz abacaxi?"), make_context())
    hint = decision.hint
    assert decision.decision is DecisionKind.SPEAK and hint is not None
    assert hint.expression == "pineapple" and hint.target_language is Language.EN
    assert hint.target_user_id == "ana" and hint.reason is Reason.ASKS_MOCHI


# ---- 6: only an explicit request to hear a word ----


@pytest.mark.parametrize(
    "ordinary",
    [
        "Fala pra mim como foi a viagem",
        "Me conta, fala pra mim o que aconteceu",
        "Ben pronounces it weirdly",
        "I can't pronounce my own street",
        "The pronunciation of this language is hard to me",
        "Ela tem uma pronúncia ótima",
        "A pronúncia dele é engraçada",
    ],
)
def test_ordinary_talk_does_not_ask_to_hear_a_word(ordinary: str) -> None:
    assert not wants_to_hear(ordinary), ordinary


@pytest.mark.parametrize(
    "request_to_hear",
    [
        "How do you pronounce receipt?",
        "How is it pronounced?",
        "Could you please pronounce that for me?",
        "What's the pronunciation?",
        "Can you say the word again?",
        "Can you say it again?",
        "Como se pronuncia recibo?",
        "Como é a pronúncia de queue?",
        "Você pode pronunciar isso?",
        "Fala de novo?",
        "Fala pra mim?",
        "Repete a palavra, por favor",
    ],
)
def test_an_explicit_request_to_hear_a_word_is_one(request_to_hear: str) -> None:
    assert wants_to_hear(request_to_hear), request_to_hear


# ---- 7: the hint does not wait for Mochi's own words ----


async def test_a_hint_does_not_wait_for_a_character_reply_that_never_comes() -> None:
    mochi = GatedCharacterModel("[mood happy] Fork!")
    brain = _brain(FORK)
    brain.speak_as(mochi)
    decision = await asyncio.wait_for(
        brain.decide(make_turn("Mochi, " + GARFO.lower()), make_context()), timeout=1.0
    )
    assert decision.hint is not None and decision.hint.expression == "fork"
    assert mochi.requests  # it was asked, the hint just did not wait for it


async def test_a_character_reply_that_never_comes_falls_back_to_the_plain_answer() -> None:
    mochi = GatedCharacterModel("never heard")
    brain = _brain(PINEAPPLE, IntelligenceSettings(character_timeout_seconds=0.01))
    brain.speak_as(mochi)
    decision = await brain.decide(make_turn("Oi Mochi, como se diz abacaxi?"), make_context())
    assert decision.speak is not None and decision.speak.text == "Você pode dizer: pineapple."
    assert decision.hint is not None and decision.hint.expression == "pineapple"


async def test_a_quick_character_reply_still_rides_with_the_hint() -> None:
    brain = _brain(FORK)
    brain.speak_as(FakeCharacterModel("[mood happy] Fork!"))
    decision = await brain.decide(make_turn("Mochi, " + GARFO.lower()), make_context())
    assert decision.hint is not None and decision.speak is not None


# ---- 8: no confidence is no certainty ----


def _asked(confidence: object) -> ModelSuggestion:
    fields = FORK.model_dump() | {"confidence": confidence}
    return ModelSuggestion.model_validate(fields)


async def _watched(model: ModelSuggestion) -> Decision:
    return await _brain(model).decide(make_turn(GARFO, 60), make_context())


async def test_a_model_hint_without_a_confidence_is_not_shown() -> None:
    assert (await _watched(_asked(None))).decision is DecisionKind.IGNORE
    assert (await _watched(_asked(0.95))).decision is DecisionKind.SHOW_HINT


async def test_a_rule_hit_in_the_lexicon_needs_no_confidence() -> None:
    brain = _brain(None)
    decision = await brain.decide(make_turn("I need to adiar my meeting tomorrow."), make_context())
    assert decision.hint is not None and decision.hint.expression == "postpone"


# ---- 9: a failing hint model leaves a metadata-only trace ----

REQUEST = ModelRequest(
    text="my secret sentence", recent_texts=[], focus=Language.EN, candidate_reasons=[]
)


def _model(reply: HttpResponse | HttpTransportError, logger: FakeEventLogger) -> OpenAiHintModel:
    http = FakeHttpClient([reply])
    return OpenAiHintModel(http, "https://llm.example/v1", "m", "sk-secret", 2.0).logging(logger)


@pytest.mark.parametrize(
    ("reply", "why"),
    [
        (HttpResponse(401, "bad key sk-secret my secret sentence"), "HTTP 401"),
        (HttpTransportError("my secret sentence down"), "HttpTransportError"),
        (HttpResponse(200, "not json my secret sentence"), "ValidationError"),
        (HttpResponse(200, '{"choices": []}'), "IndexError"),
    ],
)
async def test_a_failed_hint_call_is_logged_without_the_sentence_or_key(
    reply: HttpResponse | HttpTransportError, why: str
) -> None:
    logger = FakeEventLogger()
    assert await _model(reply, logger).suggest(REQUEST) is None
    [(name, fields)] = logger.lines
    assert name == "hint_model_failed" and fields["why"] == why and fields["model"] == "m"
    assert "secret" not in json.dumps(fields)


async def test_a_good_hint_call_logs_nothing() -> None:
    logger = FakeEventLogger()
    body = json.dumps({"choices": [{"message": {"content": '{"decision": "IGNORE"}'}}]})
    assert await _model(HttpResponse(200, body), logger).suggest(REQUEST) is not None
    assert logger.lines == []


async def _hint_model_said(confidence: str) -> Decision:
    content = json.dumps({**FORK.model_dump(), "confidence": json.loads(confidence)})
    body = json.dumps({"choices": [{"message": {"content": content}}]})
    http = FakeHttpClient([HttpResponse(200, body)])
    model = OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0)
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=model)
    return await brain.decide(make_turn(GARFO, 60), make_context())


@pytest.mark.parametrize("confidence", ['"high"', "true", "null", '"0.95"'])
async def test_a_confidence_that_is_not_a_number_is_not_a_certainty(confidence: str) -> None:
    assert (await _hint_model_said(confidence)).decision is DecisionKind.IGNORE


async def test_a_numeric_confidence_from_the_real_adapter_is_shown() -> None:
    assert (await _hint_model_said("95")).decision is DecisionKind.SHOW_HINT
