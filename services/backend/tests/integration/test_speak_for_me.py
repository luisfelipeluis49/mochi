"""Speak for me (DECISIONS D-64, D-69): someone asks Mochi to speak for them, and from then on it
says every sentence of the meeting in the other language, whoever said it, until told to stop."""

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
from mochi_backend.intelligence.speak_for_me import SpeakForMe
from mochi_contracts import DecisionKind, Language, SessionMode, Speak, Turn
from tests.factories import ANA, make_context, make_turn
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_interpret_model import FakeInterpretModel
from tests.harness import HOME, Harness, make_harness
from tests.unit.test_explaining import _reply

ADIAR_PT = "A gente precisa adiar o lançamento para a semana que vem."
ADIAR_EN = "We need to postpone the launch to next week."
SUPPLIER_EN = "I think we should talk to the supplier first."
SUPPLIER_PT = "Acho que a gente deveria falar com o fornecedor primeiro."
SCRIPT = {"adiar o lançamento": ADIAR_EN, "talk to the supplier": SUPPLIER_PT}


async def _meeting(**env: str) -> tuple[Harness, FakeInterpretModel]:
    model = FakeInterpretModel(SCRIPT)
    harness = make_harness(env=env or None, interprets=model)
    await harness.container.sessions.start()
    return harness, model


async def _says(harness: Harness, text: str, who: str | None = None) -> str:
    """One sentence, in a voice the device may or may not know; returns what Mochi says aloud."""
    harness.container.core.store.speaker = who
    return (await harness.say(text)).reply


async def test_anyone_turns_it_on_and_every_sentence_is_said_in_the_other_language() -> None:
    harness, model = await _meeting()
    [home] = await harness.connect_all(HOME)
    welcome = await _says(harness, "Hey Mochi, speak for me.")  # no voice Mochi knows: no matter
    assert "translate" in welcome and "Mochi, pode parar" in welcome  # both ways out are named
    assert await _says(harness, ADIAR_PT) == ADIAR_EN
    spoken = [e.payload for e in home.events if isinstance(e.payload, Speak)][-1]
    assert (spoken.text, spoken.language) == (ADIAR_EN, Language.EN)
    assert await _says(harness, SUPPLIER_EN, "ben") == SUPPLIER_PT  # the colleague, the other way
    ways = [(asked.source, asked.target) for asked in model.requests]
    assert ways == [(Language.PT_BR, Language.EN), (Language.EN, Language.PT_BR)]
    assert harness.container.core.intelligence.words_for("ana") == []  # nothing to learn here


async def test_a_voice_command_turns_it_off_and_it_starts_off_in_every_session() -> None:
    harness, model = await _meeting()
    assert await _says(harness, ADIAR_PT) == ""  # nobody asked yet
    await _says(harness, "Oi Mochi, fala por mim, por favor.")
    assert await _says(harness, ADIAR_PT) == ADIAR_EN
    assert await _says(harness, "Mochi, pode parar.") == "Combinado, agora é com vocês."
    assert await _says(harness, ADIAR_PT) == ""
    await _says(harness, "Mochi, translate for us.")
    await harness.container.sessions.stop()
    await harness.container.sessions.start()
    assert await _says(harness, ADIAR_PT) == "" and len(model.requests) == 1
    off, unused = await _meeting(MOCHI_SPEAK_FOR_ME="false")
    await _says(off, "Hey Mochi, speak for me.")
    assert await _says(off, ADIAR_PT) == "" and unused.requests == []


def _mode(model: FakeInterpretModel | None = None) -> SpeakForMe:
    return SpeakForMe(model or FakeInterpretModel(SCRIPT), Lexicon.load(), IntelligenceSettings())


def _by(text: str, who: str | None = None, seconds: float = 0.0) -> Turn:
    return make_turn(text, seconds).model_copy(update={"speaker_user_id": who})


@pytest.mark.parametrize(
    "command",
    [
        "Hey Mochi, speak for me.",
        "Mochi can you talk for me please",
        "Mochi, translate for us.",
        "Oi Mochi, fala por mim.",
        "Mochi, pode falar por mim?",
        "Moshi, fale por mim",
        "Mochi, traduz pra gente.",
    ],
)
async def test_the_ways_of_asking(command: str) -> None:
    mode = _mode()
    answer = await mode.take(_by(command), make_context())
    assert answer is not None and answer.decision is DecisionKind.SPEAK
    assert mode.on


@pytest.mark.parametrize(
    "command",
    [
        "Mochi, stop speaking for me.",
        "Mochi, para de falar por mim.",  # seen live: it holds "falar por mim" and turned it ON
        "Moshi, pode parar de falar por mim?",
        "Para de falar por mim, por favor.",
        "Mochi, stop translating for us.",
        "Mochi, I'll speak myself.",
        "Mochi, pode parar.",
        "Mochi, stop.",
        "Okay Mochi, chega, obrigada.",
        "Moji, pode parar.",  # the name misheard: the stop phrase and nothing else is enough
        "Hey Moshe, stop.",
        "Mochi, stop translating.",
        "Stop, Mochi.",
        "Pode parar, Mochi.",
        "Mochi, para.",
        "Mochi. Stop.",
        "Mochi, stop, okay?",
        "Mochi, pode parar. Então, voltando ao assunto.",  # more said after it in the same turn
        "Mochi, não precisa falar por mim.",  # the words that turn it on, with a no
        "Mochi, you don't need to translate for us anymore.",
    ],
)
async def test_the_ways_of_stopping_it(command: str) -> None:
    mode = _mode()
    await mode.take(_by("Mochi, speak for me.", "ana"), make_context())
    answer = await mode.take(_by(command, "ben", 5), make_context())  # anyone may stop it
    assert answer is not None and answer.speak is not None
    assert "mood" not in answer.speak.text  # the goodbye line, not the welcome again
    assert not mode.on


@pytest.mark.parametrize(
    "sentence",
    [
        "Oi Mochi, como eu falo fila em inglês?",  # "eu falo" is not "I'll speak"
        "Mochi, quando chega o relatório?",  # "chega": it arrives
        "Mochi, how do you say stop sign in Portuguese?",
        "Please stop talking, Ben.",  # to a person
        "Pode parar.",  # no name at all: a sentence of the meeting
        "A gente pode parar de adiar o lançamento?",
        "Mochi, isso é para o cliente de São Paulo?",  # "para": for
        "Monday, stop by my office.",
        "Mostra, pode parar aí.",
    ],
)
async def test_a_stop_word_in_a_question_or_in_the_meetings_own_talk_does_not_turn_it_off(
    sentence: str,
) -> None:
    mode = _mode()
    await mode.take(_by("Mochi, speak for me."), make_context())
    await mode.take(_by(sentence, None, 5), make_context())
    assert mode.on


async def test_what_is_not_a_command_and_what_is_not_translated() -> None:
    mode = _mode()
    context = make_context()
    assert await mode.take(_by("Can you speak for me at the meeting, Ben?"), context) is None
    assert await mode.take(_by("Mochi, stop speaking for me."), context) is None  # it was off
    assert await mode.take(_by(ADIAR_PT), context) is None and not mode.on
    await mode.take(_by("Mochi, speak for me."), context)
    assert await mode.take(_by("Mochi, como se diz fila em inglês?"), context) is None  # for Mochi
    assert await mode.take(_by("Hum, é."), context) is None  # the model: NOTHING
    review = make_context(participants=[ANA], mode=SessionMode.REVIEW)
    assert await mode.take(_by(ADIAR_PT), review) is None
    mode.fresh_session()
    assert not mode.on


@pytest.mark.parametrize(
    "said",
    [
        "Mochi, don't translate for us.",
        "Mochi, não precisa falar por mim.",
        "I asked Mochi to speak for me yesterday.",
        "Mochi, para de falar por mim.",  # it was off: nothing to stop, and nothing to start
    ],
)
async def test_saying_no_with_the_words_that_ask_does_not_turn_it_on(said: str) -> None:
    mode = _mode()
    assert await mode.take(_by(said), make_context()) is None
    assert not mode.on


async def test_the_model_decides_which_way_a_short_sentence_goes() -> None:
    # after an English sentence "Quanto custa?" is guessed English; the model knows better
    model = FakeInterpretModel({"quanto custa": "How much does it cost?"}, answers_in="en")
    mode = _mode(model)
    await mode.take(_by("Mochi, speak for me."), make_context())
    said = await mode.take(_by("Quanto custa?", None, 4), make_context())
    assert said is not None and said.speak is not None
    assert (said.speak.text, said.speak.language) == ("How much does it cost?", Language.EN)


async def test_its_welcome_coming_back_neither_stops_it_nor_is_translated() -> None:
    model = FakeInterpretModel(SCRIPT)
    mode = _mode(model)
    welcome = await mode.take(_by("Mochi, speak for me."), make_context())
    assert welcome is not None and welcome.speak is not None
    heard = welcome.speak.text.partition("] ")[2]  # as a microphone would hear it
    for echo in (heard, "Okay, I'll translate for you."):
        again = await mode.take(_by(echo, None, 5), make_context())
        assert again is not None and again.decision is DecisionKind.IGNORE
    assert mode.on and model.requests == []
    stop = await mode.take(_by("Mochi, pode parar.", None, 9), make_context())  # a person
    assert stop is not None and not mode.on


async def test_its_own_sentence_coming_back_is_not_translated_again() -> None:
    model = FakeInterpretModel(SCRIPT)
    mode = _mode(model)
    await mode.take(_by("Mochi, speak for me."), make_context())
    said = await mode.take(_by(ADIAR_PT, None, 3), make_context())
    assert said is not None and said.speak is not None and said.speak.text == ADIAR_EN
    echo = await mode.take(_by(ADIAR_EN, None, 9), make_context())  # the microphone heard Mochi
    assert echo is not None and echo.decision is DecisionKind.IGNORE
    assert len(model.requests) == 1


async def test_a_short_sentence_goes_on_in_the_language_of_the_one_before() -> None:
    model = FakeInterpretModel(SCRIPT)
    mode = _mode(model)
    await mode.take(_by("Mochi, speak for me."), make_context())
    await mode.take(_by(ADIAR_PT, None, 3), make_context())
    await mode.take(_by("Ok.", None, 6), make_context())
    assert [asked.source for asked in model.requests] == [Language.PT_BR, Language.PT_BR]


async def test_a_model_that_fails_or_echoes_says_nothing_and_the_openai_adapter() -> None:
    class Broken(FakeInterpretModel):
        async def interpret(self, request: InterpretRequest) -> Interpretation | None:
            raise RuntimeError("boom")

    for model in (Broken(), FakeInterpretModel({"adiar": ADIAR_PT}), NullInterpretModel()):
        mode = _mode(model)  # type: ignore[arg-type]
        await mode.take(_by("Mochi, speak for me."), make_context())
        assert await mode.take(_by(ADIAR_PT), make_context()) is None
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


async def test_a_demo_reset_leaves_mochi_translating_for_nobody() -> None:
    harness, _ = await _meeting()
    await _says(harness, "Hey Mochi, speak for me.")
    harness.container.core.intelligence.reset()
    assert await _says(harness, ADIAR_PT) == ""
