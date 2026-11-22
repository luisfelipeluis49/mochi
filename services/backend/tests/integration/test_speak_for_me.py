"""Speak for me (DECISIONS D-64): a person with a registered voice asks Mochi to speak for them,
talks in their own language, and Mochi says each sentence in the meeting's, until told to stop."""

import pytest

from mochi_backend.intelligence.interpret_port import (
    Interpretation,
    InterpretRequest,
    NullInterpretModel,
)
from mochi_backend.intelligence.json_chat import JsonChat, JsonChatConfig
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.openai_interpret_model import (
    OpenAiInterpretModel,
    parse_interpretation,
)
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.speak_for_me import SpeakForMe, home_of
from mochi_contracts import DecisionKind, Language, SessionMode, Speak, Turn
from tests.factories import ANA, BEN, make_context, make_turn
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_interpret_model import FakeInterpretModel
from tests.harness import HOME, Harness, make_harness
from tests.unit.test_explaining import _reply

ADIAR_PT = "A gente precisa adiar o lançamento para a semana que vem."
ADIAR_EN = "We need to postpone the launch to next week."
SCRIPT = {"adiar o lançamento": ADIAR_EN, "talk to the supplier": "Vamos falar com o fornecedor."}


async def _meeting(**env: str) -> tuple[Harness, FakeInterpretModel]:
    model = FakeInterpretModel(SCRIPT)
    harness = make_harness(env=env or None, interprets=model)
    await harness.container.sessions.start()
    return harness, model


async def _says(harness: Harness, who: str | None, text: str) -> str:
    """One sentence in the voice the device recognised; returns what Mochi says aloud."""
    harness.container.core.store.speaker = who
    return (await harness.say(text)).reply


async def test_a_known_voice_turns_it_on_and_her_sentences_are_said_in_english() -> None:
    harness, model = await _meeting()
    [home] = await harness.connect_all(HOME)
    welcome = await _says(harness, "ana", "Hey Mochi, speak for me.")
    assert "speak for you" in welcome and "Mochi, pode parar" in welcome  # the way out, in hers
    assert await _says(harness, "ana", ADIAR_PT) == ADIAR_EN
    spoken = [e.payload for e in home.events if isinstance(e.payload, Speak)][-1]
    assert (spoken.text, spoken.language) == (ADIAR_EN, Language.EN)
    [asked] = model.requests
    assert (asked.source, asked.target, asked.text) == (Language.PT_BR, Language.EN, ADIAR_PT)
    assert harness.container.core.intelligence.words_for("ana") == []  # nothing to learn here


async def test_only_her_own_language_is_said_for_her_and_nobody_elses_sentences_are() -> None:
    harness, model = await _meeting()
    await _says(harness, "ana", "Oi Mochi, fala por mim, por favor.")
    assert await _says(harness, "ana", "I agree with that plan.") == ""  # she said it herself
    assert await _says(harness, "ben", "Vamos adiar o lançamento então.") == ""  # Ben did not ask
    assert await _says(harness, "ben", "Shall we move on to the budget?") == ""
    assert model.requests == []
    assert await _says(harness, None, ADIAR_PT) == ADIAR_EN  # a voice not named, in her language


async def test_a_voice_command_turns_it_off_again() -> None:
    harness, model = await _meeting()
    await _says(harness, "ana", "Mochi, speak for me.")
    stopped = await _says(harness, "ana", "Mochi, stop speaking for me.")
    assert "over to you" in stopped.lower()
    assert await _says(harness, "ana", ADIAR_PT) == "" and model.requests == []
    await _says(harness, "ana", "Mochi, fala por mim.")
    assert "com você" in await _says(harness, "ana", "Pode parar de falar por mim, obrigada.")
    await _says(harness, "ana", "Mochi, speak for me.")
    await _says(harness, None, "Mochi, pode parar.")  # nobody known says stop: better silent
    assert await _says(harness, "ana", ADIAR_PT) == ""


async def test_it_needs_a_voice_mochi_knows_and_starts_off_in_every_session() -> None:
    harness, model = await _meeting()
    refused = await _says(harness, None, "Hey Mochi, speak for me.")
    assert "whose voice I know" in refused
    assert await _says(harness, None, ADIAR_PT) == "" and model.requests == []
    await _says(harness, "ana", "Mochi, speak for me.")
    await harness.container.sessions.stop()
    await harness.container.sessions.start()
    assert await _says(harness, "ana", ADIAR_PT) == ""  # a new meeting: she has to ask again


async def test_it_works_the_other_way_round_and_can_be_switched_off() -> None:
    harness, _ = await _meeting()
    await _says(harness, "ben", "Mochi, speak for me.")
    said = await _says(harness, "ben", "I think we should talk to the supplier first.")
    assert said == "Vamos falar com o fornecedor."
    off, model = await _meeting(MOCHI_SPEAK_FOR_ME="false")
    await _says(off, "ana", "Hey Mochi, speak for me.")
    assert await _says(off, "ana", ADIAR_PT) == "" and model.requests == []


def _mode(model: FakeInterpretModel | None = None) -> SpeakForMe:
    return SpeakForMe(model or FakeInterpretModel(SCRIPT), Lexicon.load(), IntelligenceSettings())


def _by(text: str, who: str | None, seconds: float = 0.0) -> Turn:
    return make_turn(text, seconds).model_copy(update={"speaker_user_id": who})


@pytest.mark.parametrize(
    "command",
    [
        "Hey Mochi, speak for me.",
        "Mochi can you talk for me please",
        "Oi Mochi, fala por mim.",
        "Mochi, pode falar por mim?",
        "Moshi, fale por mim",
    ],
)
async def test_the_ways_of_asking(command: str) -> None:
    mode = _mode()
    answer = await mode.take(_by(command, "ana"), make_context())
    assert answer is not None and answer.decision is DecisionKind.SPEAK
    assert mode.speaking_for == ["ana"]


@pytest.mark.parametrize(
    "command",
    [
        "Mochi, stop speaking for me.",
        "Mochi, para de falar por mim.",  # seen live: it holds "falar por mim" and turned it ON
        "Moshi, pode parar de falar por mim?",
        "Para de falar por mim, por favor.",
        "Mochi, I'll speak myself.",
        "Mochi, pode parar.",
        "Mochi, stop.",
        "Okay Mochi, chega, obrigada.",
    ],
)
async def test_the_ways_of_stopping_it(command: str) -> None:
    mode = _mode()
    await mode.take(_by("Mochi, speak for me.", "ana"), make_context())
    answer = await mode.take(_by(command, "ana", 5), make_context())
    assert answer is not None and answer.speak is not None
    assert "mood" not in answer.speak.text  # the goodbye line, not the welcome again
    assert mode.speaking_for == []


async def test_what_is_not_a_command_and_what_is_not_said() -> None:
    mode = _mode()
    context = make_context()
    assert await mode.take(_by("Can you speak for me at the meeting, Ben?", "ana"), context) is None
    assert await mode.take(_by("Mochi, stop speaking for me.", "ana"), context) is None  # was off
    assert mode.speaking_for == []
    await mode.take(_by("Mochi, speak for me.", "ana"), context)
    assert await mode.take(_by("Please stop talking, Ben.", "ana"), context) is None  # to a person
    assert mode.speaking_for == ["ana"]
    assert await mode.take(_by("Mochi, como se diz fila em inglês?", "ana"), context) is None
    assert await mode.take(_by("Hum, é.", "ana"), context) is None  # the model: NOTHING
    review = make_context(participants=[ANA], mode=SessionMode.REVIEW)
    assert await mode.take(_by(ADIAR_PT, "ana"), review) is None
    mode.fresh_session()
    assert mode.speaking_for == [] and home_of(BEN) is Language.EN


async def test_a_model_that_fails_or_echoes_says_nothing_and_the_openai_adapter() -> None:
    class Broken(FakeInterpretModel):
        async def interpret(self, request: InterpretRequest) -> Interpretation | None:
            raise RuntimeError("boom")

    for model in (Broken(), FakeInterpretModel({"adiar": ADIAR_PT}), NullInterpretModel()):
        mode = _mode(model)  # type: ignore[arg-type]
        await mode.take(_by("Mochi, speak for me.", "ana"), make_context())
        assert await mode.take(_by(ADIAR_PT, "ana"), make_context()) is None
    answer = '{"decision": "SAY", "sentence": "We need to postpone it."}'
    http = FakeHttpClient([_reply(answer), _reply("nope")])
    config = JsonChatConfig("https://llm/v1", "tiny", "k", 2.0)
    adapter = OpenAiInterpretModel(JsonChat(http, config, "interpret"))
    asked = InterpretRequest(
        text=ADIAR_PT, recent_texts=["Why?"], source=Language.PT_BR, target=Language.EN
    )
    said = await adapter.interpret(asked)
    assert said is not None and said.sentence == "We need to postpone it."
    sent = http.posts[0].payload
    assert isinstance(sent, dict) and "adiar" in str(sent["messages"])
    assert await adapter.interpret(asked) is None and parse_interpretation("[]") is None
    await adapter.warm_up()


@pytest.mark.parametrize(
    "question",
    [
        "Oi Mochi, como eu falo fila em inglês?",  # "eu falo" is not "I'll speak"
        "Mochi, quando chega o relatório?",  # "chega": it arrives
        "Mochi, how do you say stop sign in Portuguese?",
    ],
)
async def test_a_question_for_mochi_with_a_stop_word_in_it_does_not_turn_it_off(
    question: str,
) -> None:
    mode = _mode()
    await mode.take(_by("Mochi, speak for me.", "ana"), make_context())
    assert await mode.take(_by(question, "ana", 5), make_context()) is None
    assert mode.speaking_for == ["ana"]


@pytest.mark.parametrize(
    ("command", "voice"),
    [
        ("Moji, pode parar.", "ana"),  # the name misheard: the stop phrase alone is enough from her
        ("Pode parar.", None),  # no voice recognised, and Mochi speaks for one person
        ("Hey Moshe, stop.", "ana"),
        ("Mochi, pode parar.", "ben"),  # the device took her voice for Ben's: it still stops
    ],
)
async def test_the_stop_phrase_works_with_a_misheard_name_or_a_mistaken_voice(
    command: str, voice: str | None
) -> None:
    mode = _mode()
    await mode.take(_by("Mochi, speak for me.", "ana"), make_context())
    answer = await mode.take(_by(command, voice, 5), make_context())
    assert answer is not None and answer.speak is not None
    assert mode.speaking_for == []


async def test_a_sentence_that_only_holds_a_stop_word_is_still_said_for_her() -> None:
    mode = _mode()
    await mode.take(_by("Mochi, speak for me.", "ana"), make_context())
    assert await mode.take(_by("Pode parar.", "ben", 5), make_context()) is None  # Ben, to someone
    said = await mode.take(
        _by("A gente pode parar de adiar o lançamento?", "ana", 6), make_context()
    )
    assert mode.speaking_for == ["ana"] and said is not None  # a sentence, not the command


async def test_a_demo_reset_leaves_mochi_speaking_for_nobody() -> None:
    harness, _ = await _meeting()
    await _says(harness, "ana", "Hey Mochi, speak for me.")
    harness.container.core.intelligence.reset()
    assert await _says(harness, "ana", ADIAR_PT) == ""
