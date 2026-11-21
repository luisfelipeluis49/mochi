"""Mochi answers in character when it is spoken to, and stays quiet otherwise."""

import json

import pytest

from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus, Exchange
from mochi_backend.intelligence.mochi_talk import spoken_line
from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.openai_character_model import (
    CharacterModelConfig,
    OpenAiCharacterModel,
    messages_for,
    system_prompt,
)
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import DecisionKind, Language, Reason
from tests.factories import active_round, make_context, make_turn
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_sender import FakeEventLogger

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
    woken.session_started(woken=True)
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


async def test_someone_who_woke_mochi_keeps_its_attention_for_the_whole_session() -> None:
    """Seen live: a minute after its last answer, "Are you still there?" got silence."""
    clock = FakeClock()
    mochi = FakeCharacterModel("[mood happy] Bye-bye!", "[mood happy] Still here!")
    brain = _brain(mochi, clock)
    brain.session_started(woken=True)
    await brain.decide(make_turn("I need to go, tchau tchau!"), make_context())
    clock.advance(60)
    decision = await brain.decide(make_turn("Are you still there?"), make_context())
    assert decision.decision is DecisionKind.SPEAK and mochi.requests[1].woken is True


def _two_minds(mochi: FakeCharacterModel, clock: FakeClock) -> Intelligence:
    """Mochi's scripted lines, and a hint model that knows one word outside the lexicon."""
    fork = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.CODE_SWITCH,
        expression="fork",
        meaning="garfo",
        confidence=0.9,
    )
    tuning = IntelligenceSettings(character_timeout_seconds=6.0, follow_up_seconds=15.0)
    brain = Intelligence(
        clock=clock, ids=SequentialIdGenerator(), model=FakeHintModel(fork), settings=tuning
    )
    brain.speak_as(mochi)
    return brain


async def test_told_to_just_listen_mochi_only_watches_and_helps_silently() -> None:
    """The main promise: two people talk, Mochi is silent, a stuck word appears on the screen."""
    clock = FakeClock()
    mochi = FakeCharacterModel("[mood happy][listen] Okay, I'll just listen.")
    brain = _two_minds(mochi, clock)
    brain.session_started(woken=True)
    agreed = await brain.decide(make_turn("We are going to talk now, just listen."), make_context())
    assert agreed.decision is DecisionKind.SPEAK
    clock.advance(3)
    stuck = await brain.decide(make_turn("Can you pass me the garfo, please?"), make_context())
    assert stuck.decision is DecisionKind.SHOW_HINT and stuck.speak is None
    assert stuck.hint is not None and stuck.hint.expression == "fork"
    assert len(mochi.requests) == 1  # Mochi itself was not asked about that sentence


async def test_its_name_gets_an_answer_and_asking_it_back_in_makes_it_chat_again() -> None:
    clock = FakeClock()
    mochi = FakeCharacterModel(
        "[listen] Okay!", "[mood happy] Queue!", "[mood happy][chat] I'm back!", "[mood happy] Yes?"
    )
    brain = _two_minds(mochi, clock)
    brain.session_started(woken=True)
    await brain.decide(make_turn("Mochi, just listen to us now."), make_context())
    named = await brain.decide(make_turn("Oi Mochi, what's the word for fila?"), make_context())
    assert named.decision is DecisionKind.SPEAK  # its name still works while it only watches
    clock.advance(60)
    silent = await brain.decide(make_turn("That was a good film, right?"), make_context())
    assert silent.speak is None and len(mochi.requests) == 2
    await brain.decide(make_turn("Hey Mochi, you can talk with us again."), make_context())
    clock.advance(60)
    chatting = await brain.decide(make_turn("So what do you think?"), make_context())
    assert chatting.decision is DecisionKind.SPEAK and len(mochi.requests) == 4


async def test_during_a_round_mochi_only_answers_to_its_name() -> None:
    mochi = FakeCharacterModel("[mood happy] Hello!")
    brain = _brain(mochi)
    brain.session_started(woken=True)
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
    assert roles == ["system", "user", "assistant", "system", "system", "system", "user"]
    assert "umbrella" in json.dumps(messages[3]) and "[quiet]" in json.dumps(messages[4])
    assert "so your reply is in English" in json.dumps(messages[5])
    assert messages[-1] == {"role": "user", "content": "Umbrella?"}


def test_the_reply_language_and_how_likely_the_sentence_is_for_mochi_are_spelled_out() -> None:
    overheard = CharacterRequest(
        text="Tudo bem?", history=[], status=DeviceStatus(), named=False, language=Language.PT_BR
    )
    notes = json.dumps(messages_for(overheard, "PROMPT"), ensure_ascii=False)
    assert (
        "so your reply is in Brazilian Portuguese" in notes
        and "meant for the other person" in notes
    )
    woken = overheard.model_copy(update={"woken": True})
    assert "most likely for you" in json.dumps(messages_for(woken, "PROMPT"))
    named = CharacterRequest(text="Oi Mochi!", history=[], status=DeviceStatus())
    assert "[quiet]" not in json.dumps(messages_for(named, "PROMPT"))


async def test_mochi_is_told_the_language_of_each_sentence_and_whether_it_was_woken() -> None:
    mochi = FakeCharacterModel("[mood happy] ok")
    brain = _brain(mochi)
    brain.session_started(woken=True)
    await brain.decide(make_turn("How is your temperature?"), make_context())
    await brain.decide(make_turn("Você está quente?"), make_context())
    await brain.decide(make_turn("Coca-Cola?"), make_context())  # unclear: follows the last one
    assert [r.language for r in mochi.requests] == [Language.EN, Language.PT_BR, Language.PT_BR]
    assert all(r.woken for r in mochi.requests)
    brain.session_started(woken=False)  # the operator started this one: two people talking
    await brain.decide(make_turn("Hi Mochi, are you there?"), make_context())
    assert mochi.requests[-1].woken is False and mochi.requests[-1].history == []


async def test_when_the_hint_model_is_needed_mochi_does_not_wait_for_it() -> None:
    """Both models are asked at once: the word then reaches the screens but not Mochi's line."""
    hints = FakeHintModel(
        ModelSuggestion(
            decision="SHOW_HINT", reason=Reason.SAYS_UNKNOWN, expression="cancel", confidence=0.9
        )
    )
    mochi = FakeCharacterModel("[mood happy] ok")
    tuning = IntelligenceSettings(character_timeout_seconds=6.0, follow_up_seconds=15.0)
    brain = Intelligence(
        clock=FakeClock(), ids=SequentialIdGenerator(), model=hints, settings=tuning
    )
    brain.speak_as(mochi)
    brain.session_started(woken=True)
    decision = await brain.decide(make_turn("How do you say cancelar?"), make_context())
    assert decision.decision is DecisionKind.SPEAK and decision.hint is not None
    assert decision.hint.expression == "cancel" and mochi.requests[0].word is None


REQUEST = CharacterRequest(text="Hi Mochi!", history=[], status=DeviceStatus())
GOOD = json.dumps({"choices": [{"message": {"content": "[mood happy] Oi!"}}]})


def _config(effort: str = "") -> CharacterModelConfig:
    return CharacterModelConfig("https://llm.example/v1/", "gpt-x", "secret-key", 6.0, effort)


async def test_openai_character_model_sends_the_prompt_and_returns_the_line() -> None:
    http = FakeHttpClient([HttpResponse(200, GOOD)])
    model = OpenAiCharacterModel(http, _config())
    assert await model.reply(REQUEST) == "[mood happy] Oi!"
    post = http.posts[0]
    assert post.url == "https://llm.example/v1/chat/completions"
    assert post.headers["Authorization"] == "Bearer secret-key" and post.timeout_seconds == 6.0
    assert isinstance(post.payload, dict) and post.payload["model"] == "gpt-x"
    assert "You are Mochi" in json.dumps(post.payload["messages"])
    assert post.payload["max_completion_tokens"] == 256 and "max_tokens" not in post.payload
    assert "reasoning_effort" not in post.payload


async def test_a_model_that_would_think_first_is_told_to_answer_at_once() -> None:
    http = FakeHttpClient([HttpResponse(200, GOOD)])
    await OpenAiCharacterModel(http, _config("none")).reply(REQUEST)
    assert isinstance(http.posts[0].payload, dict)
    assert http.posts[0].payload["reasoning_effort"] == "none"


async def test_a_failed_reply_is_explained_in_the_log() -> None:
    logger = FakeEventLogger()
    refused = HttpResponse(404, '{"error": {"message": "Your organization must be verified"}}')
    model = OpenAiCharacterModel(FakeHttpClient([refused]), _config(), logger)
    assert await model.reply(REQUEST) is None
    [(name, fields)] = logger.lines
    assert name == "character_model_failed" and "must be verified" in str(fields["why"])


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
    model = OpenAiCharacterModel(FakeHttpClient([reply]), _config())
    assert await model.reply(REQUEST) is None
