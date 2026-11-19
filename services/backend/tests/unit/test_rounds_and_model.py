"""Describe & Guess engine and the OpenAI-compatible model adapter."""

import json

import pytest

from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import ModelRequest, NullHintModel
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.intelligence.round_engine import RoundEngine
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import (
    ActivityCommand,
    GameState,
    Language,
    LearningEvent,
    LearningState,
    Reason,
    RoundResult,
    SessionContext,
    StateChange,
    WordSource,
)
from tests.factories import ANA, make_context
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_http_client import FakeHttpClient

START_ROUND = ActivityCommand(type="start", result=None)


def _engine() -> RoundEngine:
    return RoundEngine(FakeClock(), SequentialIdGenerator(), Lexicon.load())


def _saved(expression: str, state: LearningState = LearningState.DISCOVERED) -> LearningEvent:
    return LearningEvent(
        learning_event_id=f"learn_{expression}",
        user_id="ana",
        target_language=Language.EN,
        expression=expression,
        meaning=None,
        detection_signal=Reason.CODE_SWITCH,
        hint_id=None,
        learning_state=state,
        state_history=[StateChange(learning_state=state, at="2026-11-19T16:00:00.000Z")],
    )


def _with_words(*events: LearningEvent) -> SessionContext:
    context = make_context()
    return context.model_copy(update={"learning_events": {"ana": list(events), "ben": []}})


def test_first_round_uses_a_stock_word_and_hides_it() -> None:
    result = _engine().handle(START_ROUND, make_context())
    assert result.activity.state is GameState.ACTIVE_ROUND
    assert result.activity.word_source is WordSource.STOCK
    assert result.private_prompt is not None and result.private_prompt.secret_word == "umbrella"
    assert "umbrella" not in result.activity.model_dump_json()
    assert result.speak is not None and result.speak.text == "Ben describes. Ana guesses!"


def test_round_prefers_newest_describable_word_the_learner_needed() -> None:
    words = _with_words(_saved("postpone"), _saved("receipt"), _saved("umbrella"))
    # newest first: postpone is not describable, so the newest describable one is receipt
    result = _engine().handle(START_ROUND, words)
    assert result.activity.word_source is WordSource.LEARNING_EVENT
    assert result.private_prompt is not None
    assert result.private_prompt.secret_word == "receipt"
    assert result.private_prompt.source_learning_event_id == "learn_receipt"


def test_reinforced_words_are_not_repeated() -> None:
    words = _with_words(_saved("umbrella", LearningState.REINFORCED))
    assert _engine().handle(START_ROUND, words).activity.word_source is WordSource.STOCK


def test_guessed_round_reveals_the_word_and_reinforces_the_card() -> None:
    engine = _engine()
    words = _with_words(_saved("umbrella"))
    started = engine.handle(START_ROUND, words)
    playing = words.model_copy(update={"activity": started.activity})
    done = engine.handle(ActivityCommand(type="result", result=RoundResult.GUESSED), playing)
    assert done.activity.state is GameState.ROUND_RESULT
    assert done.activity.revealed_word == "umbrella"
    assert done.activity.public_instruction == "Ana got it!"
    assert [e.learning_state for e in done.learning_events] == [LearningState.REINFORCED]
    assert len(done.learning_events[0].state_history) == 2


def test_skipped_round_changes_no_cards() -> None:
    engine = _engine()
    words = _with_words(_saved("umbrella"))
    started = engine.handle(START_ROUND, words)
    playing = words.model_copy(update={"activity": started.activity})
    done = engine.handle(ActivityCommand(type="result", result=RoundResult.SKIPPED), playing)
    assert done.activity.result is RoundResult.SKIPPED and done.learning_events == []


def test_next_stock_word_follows_the_last_revealed_one() -> None:
    engine = _engine()
    first = engine.handle(START_ROUND, make_context())
    playing = make_context().model_copy(update={"activity": first.activity})
    done = engine.handle(ActivityCommand(type="result", result=RoundResult.SKIPPED), playing)
    again = make_context().model_copy(update={"activity": done.activity})
    second = engine.handle(START_ROUND, again)
    assert second.private_prompt is not None and second.private_prompt.secret_word == "suitcase"


def test_result_without_a_round_is_an_error_naming_the_state() -> None:
    command = ActivityCommand(type="result", result=RoundResult.GUESSED)
    with pytest.raises(ValueError, match="expected ACTIVE_ROUND"):
        _engine().handle(command, make_context())


def test_start_needs_two_participants() -> None:
    with pytest.raises(ValueError, match="exactly 2 participants"):
        _engine().handle(START_ROUND, make_context(participants=[ANA]))


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
