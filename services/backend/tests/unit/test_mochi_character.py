"""Mochi answers in character when it is spoken to, and stays quiet otherwise."""

import json

import pytest

from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus, Exchange
from mochi_backend.intelligence.mochi_talk import spoken_line
from mochi_backend.intelligence.openai_character_model import (
    OpenAiCharacterModel,
    messages_for,
    system_prompt,
)
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import DecisionKind
from tests.factories import active_round, make_context, make_turn
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient

ASK_WORD = "Oi Mochi, what's the word for fila?"
ASK_LOUDER = "Hi Mochi, can you speak a bit louder?"
ADIAR = "I need to adiar my meeting tomorrow."


def _brain(
    character: FakeCharacterModel, clock: FakeClock | None = None, timeout: float = 6.0
) -> Intelligence:
    tuning = IntelligenceSettings(character_timeout_seconds=timeout, follow_up_seconds=15.0)
    brain = Intelligence(
        clock=clock or FakeClock(),
        ids=SequentialIdGenerator(),
        model=FakeHintModel(),
        settings=tuning,
    )
    brain.speak_as(character)
    return brain


async def test_a_word_asked_of_mochi_is_answered_in_character_and_still_shown() -> None:
    mochi = FakeCharacterModel("[mood excited][show queue] In English we say queue!")
    decision = await _brain(mochi).decide(make_turn(ASK_WORD), make_context())
    assert decision.decision is DecisionKind.SPEAK and decision.speak is not None
    assert decision.speak.text == "[mood excited][show queue] In English we say queue!"
    assert decision.hint is not None and decision.hint.expression == "queue"
    request = mochi.requests[0]
    assert (request.word, request.meaning, request.named) == ("queue", "fila", True)


async def test_without_an_answer_from_the_model_the_fixed_line_is_spoken() -> None:
    decision = await _brain(FakeCharacterModel(None)).decide(make_turn(ASK_WORD), make_context())
    assert decision.speak is not None and decision.speak.text == "You can say: queue."


async def test_a_slow_model_falls_back_to_the_fixed_line() -> None:
    slow = FakeCharacterModel("too late", delay_seconds=0.2)
    decision = await _brain(slow, timeout=0.01).decide(make_turn(ASK_WORD), make_context())
    assert decision.speak is not None and decision.speak.text == "You can say: queue."


async def test_something_for_mochi_to_do_is_answered_only_in_character() -> None:
    mochi = FakeCharacterModel("[mood cool][volume 80] Louder it is!")
    decision = await _brain(mochi).decide(make_turn(ASK_LOUDER), make_context())
    assert decision.decision is DecisionKind.SPEAK and decision.hint is None
    assert decision.speak is not None and decision.speak.text.endswith("Louder it is!")
    silent = await _brain(FakeCharacterModel(None)).decide(make_turn(ASK_LOUDER), make_context())
    assert silent.decision is DecisionKind.IGNORE


async def test_the_next_sentence_can_answer_mochi_without_saying_its_name() -> None:
    clock = FakeClock()
    mochi = FakeCharacterModel("[mood curious] It starts with um. Any guess?", "[mood proud] Yes!")
    brain = _brain(mochi, clock)
    await brain.decide(make_turn(ASK_LOUDER), make_context())
    clock.advance(5)
    decision = await brain.decide(make_turn("Umbrella?"), make_context())
    assert decision.decision is DecisionKind.SPEAK and decision.speak is not None
    assert decision.speak.text == "[mood proud] Yes!"
    follow_up = mochi.requests[1]
    assert follow_up.named is False
    assert [e.role for e in follow_up.history] == ["user", "assistant"]


async def test_mochi_stays_out_of_a_sentence_that_was_not_for_it() -> None:
    clock = FakeClock()
    mochi = FakeCharacterModel("[mood happy] Louder it is!", "[quiet]")
    brain = _brain(mochi, clock)
    await brain.decide(make_turn(ASK_LOUDER), make_context())
    clock.advance(3)
    decision = await brain.decide(make_turn(ADIAR), make_context())
    assert decision.decision is DecisionKind.SHOW_HINT and decision.speak is None
    assert decision.hint is not None and decision.hint.expression == "postpone"


async def test_a_word_needed_in_a_follow_up_is_shown_and_taught_by_mochi() -> None:
    clock = FakeClock()
    mochi = FakeCharacterModel(
        "[mood happy] Louder it is!", "[mood proud][show postpone] Postpone!"
    )
    brain = _brain(mochi, clock)
    await brain.decide(make_turn(ASK_LOUDER), make_context())
    clock.advance(3)
    decision = await brain.decide(make_turn(ADIAR), make_context())
    assert decision.decision is DecisionKind.SPEAK and decision.speak is not None
    assert decision.hint is not None and decision.hint.expression == "postpone"
    assert len(decision.learning_events) == 1
    assert (mochi.requests[1].word, mochi.requests[1].named) == ("postpone", False)


async def test_after_a_while_only_its_name_makes_mochi_listen_again() -> None:
    clock = FakeClock()
    mochi = FakeCharacterModel("[mood happy] Louder it is!")
    brain = _brain(mochi, clock)
    await brain.decide(make_turn(ASK_LOUDER), make_context())
    clock.advance(60)
    decision = await brain.decide(make_turn("Did you watch the match yesterday?"), make_context())
    assert decision.decision is DecisionKind.IGNORE and len(mochi.requests) == 1


async def test_just_its_name_gets_a_short_answer_and_opens_the_conversation() -> None:
    mochi = FakeCharacterModel("[mood happy] Oi?", "[mood happy] I love rain.")
    brain = _brain(mochi)
    called = await brain.decide(make_turn("Oi Mochi."), make_context())
    assert called.speak is not None and called.speak.text == "[mood happy] Oi?"
    answered = await brain.decide(make_turn("What do you like?"), make_context())
    assert answered.decision is DecisionKind.SPEAK
    silent = _brain(FakeCharacterModel(None))  # without a model: silence, as before
    assert (await silent.decide(make_turn("Oi Mochi."), make_context())).speak is None


async def test_the_wake_phrase_on_the_device_opens_the_conversation() -> None:
    woken = _brain(FakeCharacterModel("[mood happy] Oi!"))
    woken.called()
    assert (await woken.decide(make_turn("Tudo bem?"), make_context())).speak is not None


async def test_its_name_without_a_greeting_lets_mochi_judge_whether_it_was_called() -> None:
    """Speech-to-text loses the greeting: "Oi Mochi" arrived as "Wait, Mochi." in a live session."""
    mochi = FakeCharacterModel("[mood sleepy][temp] Fifty-two degrees.", "[quiet]")
    brain = _brain(mochi)
    heard = await brain.decide(make_turn("Wait, Mochi. How hot are you right now?"), make_context())
    assert heard.decision is DecisionKind.SPEAK and mochi.requests[0].named is False
    about = await brain.decide(make_turn("I think Mochi is cute."), make_context())
    assert about.decision is DecisionKind.IGNORE
    no_model = _brain(FakeCharacterModel(None))
    quiet = await no_model.decide(make_turn("Wait, Mochi. How hot are you?"), make_context())
    assert quiet.decision is DecisionKind.IGNORE


async def test_during_a_round_mochi_only_answers_to_its_name() -> None:
    mochi = FakeCharacterModel("[mood happy] Hello!")
    brain = _brain(mochi)
    brain.called()
    playing = make_context(activity=active_round())
    decision = await brain.decide(make_turn("It is something you open."), playing)
    assert decision.speak is None and mochi.requests == []


async def test_mochi_knows_what_the_device_reported_and_reset_forgets_the_talk() -> None:
    mochi = FakeCharacterModel("[mood sleepy][temp] Fifty-two degrees.")
    brain = _brain(mochi)
    brain.device_status(80, 52, ["Ana"], "Ana")
    await brain.decide(make_turn("Hi Mochi, how hot are you?"), make_context())
    assert mochi.requests[0].status == DeviceStatus(
        volume=80, temperature=52, voices=["Ana"], speaker="Ana"
    )
    brain.reset()
    await brain.decide(make_turn("Hi Mochi, and now?"), make_context())
    assert mochi.requests[1].history == []


def test_silence_is_recognised_in_what_the_model_wrote() -> None:
    assert spoken_line(" [QUIET] ") is None and spoken_line("") is None
    assert spoken_line(None) is None
    assert spoken_line(" [mood happy] Oi! ") == "[mood happy] Oi!"


def test_the_prompt_says_who_mochi_is_and_what_is_true_right_now() -> None:
    prompt = system_prompt(DeviceStatus(volume=80, temperature=52, voices=["Ana"], speaker="Ana"))
    assert prompt.startswith("You are Mochi") and "{" not in prompt
    assert "speaker volume is 80 of 100" in prompt and "temperature is 52 degrees" in prompt
    assert "Voices you know: Ana. The person talking to you right now is Ana." in prompt
    assert "[quiet]" in prompt and "from 20 (quietest)" in prompt
    unknown = system_prompt(DeviceStatus())
    assert "volume is unknown" in unknown and "do not know anyone's voice yet" in unknown


def test_the_chat_carries_the_talk_so_far_and_notes_for_this_sentence() -> None:
    request = CharacterRequest(
        text="Umbrella?",
        history=[Exchange(role="user", text="a"), Exchange(role="assistant", text="b")],
        status=DeviceStatus(),
        word="umbrella",
        meaning="guarda-chuva",
        named=False,
    )
    messages = messages_for(request, "PROMPT")
    roles = [m["role"] for m in messages if isinstance(m, dict)]
    assert roles == ["system", "user", "assistant", "system", "system", "user"]
    assert "umbrella" in json.dumps(messages[3]) and "[quiet]" in json.dumps(messages[4])
    assert messages[-1] == {"role": "user", "content": "Umbrella?"}


REQUEST = CharacterRequest(text="Hi Mochi!", history=[], status=DeviceStatus())
GOOD = json.dumps({"choices": [{"message": {"content": "[mood happy] Oi!"}}]})


async def test_openai_character_model_sends_the_prompt_and_returns_the_line() -> None:
    http = FakeHttpClient([HttpResponse(200, GOOD)])
    model = OpenAiCharacterModel(http, "https://llm.example/v1/", "gpt-x", "secret-key", 6.0)
    assert await model.reply(REQUEST) == "[mood happy] Oi!"
    post = http.posts[0]
    assert post.url == "https://llm.example/v1/chat/completions"
    assert post.headers["Authorization"] == "Bearer secret-key" and post.timeout_seconds == 6.0
    assert isinstance(post.payload, dict) and post.payload["model"] == "gpt-x"
    assert "You are Mochi" in json.dumps(post.payload["messages"])


@pytest.mark.parametrize(
    "reply",
    [
        HttpResponse(500, "boom"),
        HttpResponse(200, "not json"),
        HttpResponse(200, '{"choices": []}'),
        HttpTransportError("down"),
    ],
)
async def test_openai_character_model_returns_none_on_any_failure(
    reply: HttpResponse | HttpTransportError,
) -> None:
    model = OpenAiCharacterModel(FakeHttpClient([reply]), "https://llm.example/v1", "m", "k", 6.0)
    assert await model.reply(REQUEST) is None
