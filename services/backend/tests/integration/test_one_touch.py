"""After a hint, the sentence the speaker was reaching for is shown (DECISIONS D-59); a word
someone asks for outright is said as it is shown, and the touch is gone (D-70)."""

import json

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.intelligence.json_chat import JsonChat, JsonChatConfig
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import ModelSuggestion
from mochi_backend.intelligence.openai_phrase_model import OpenAiPhraseModel, parse_phrase
from mochi_backend.intelligence.phrase_port import NullPhraseModel, PhraseAnswer, PhraseRequest
from mochi_backend.intelligence.phrasing import Phraser
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_contracts import Hint, Language, Reason, SessionMode, Speak, SuggestedPhrase
from tests.factories import ANA, make_context, make_hint, make_turn
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_phrase_model import FakePhraseModel
from tests.fakes.fake_sender import FakeSender
from tests.harness import ANA as ANA_PHONE
from tests.harness import ANA_AR, AUDIENCE, BEN, BEN_AR, HOME, Harness, make_harness
from tests.unit.test_explaining import _reply

STUCK = "Because we need to, como é que fala, adiar the release."
SAID_FOR_HER = "Because we need to postpone the release."


async def _meeting(sentence: str | None = SAID_FOR_HER) -> tuple[Harness, FakePhraseModel]:
    phrases = FakePhraseModel(sentence)
    harness = make_harness(phrases=phrases)
    await harness.container.sessions.start()
    return harness, phrases


def _phrases(sender: FakeSender) -> list[SuggestedPhrase]:
    return [e.payload for e in sender.events if isinstance(e.payload, SuggestedPhrase)]


async def _stuck(harness: Harness, text: str = STUCK) -> str:
    """Say it, let the suggestion arrive, and return the hint's id."""
    outcome = await harness.say(text)
    await harness.container.pipeline.settle()
    assert outcome.decision.hint is not None
    return outcome.decision.hint.hint_id


async def test_after_a_hint_the_sentence_goes_where_the_hint_went_and_to_the_device() -> None:
    harness, phrases = await _meeting()
    ana, ben, home, audience, hers, his = await harness.connect_all(
        ANA_PHONE, BEN, HOME, AUDIENCE, ANA_AR, BEN_AR
    )
    await harness.say("Why is the release delayed?")
    hint_id = await _stuck(harness)
    for screen in (ana, home, audience, hers):
        [phrase] = _phrases(screen)
        assert (phrase.hint_id, phrase.target_user_id, phrase.text) == (
            hint_id,
            "ana",
            SAID_FOR_HER,
        )
        assert phrase.language is Language.EN
    assert _phrases(ben) == [] and _phrases(his) == []  # it is hers, like the hint
    [asked] = phrases.requests
    assert (asked.word, asked.said, asked.language) == ("postpone", "adiar", Language.EN)
    assert asked.recent_texts == ["Why is the release delayed?"]  # what she is answering
    cards = {c.kind: json.loads(c.value) for c in harness.container.core.store.commands}
    assert cards["suggest"] == {"hint_id": hint_id, "text": SAID_FOR_HER, "language": "en"}
    assert harness.agora.spoken == []  # nothing is said until someone asks


async def test_there_is_no_touch_any_more_the_sentence_is_only_shown() -> None:
    # D-70: the touch that made Mochi say the sentence is gone, and so is its route
    harness, _ = await _meeting()
    hint_id = await _stuck(harness)
    client = TestClient(create_app(harness.container))
    assert client.post(f"/api/sessions/demo/hints/{hint_id}/say").status_code == 404
    assert harness.agora.spoken == []


async def test_a_session_that_ended_gets_no_late_sentence() -> None:
    late, _ = await _meeting()
    [ana] = await late.connect_all(ANA_PHONE)
    await late.say(STUCK)
    await late.container.sessions.stop()  # before the sentence was written
    await late.container.pipeline.settle()
    assert _phrases(ana) == [] and "phrase_suggested" not in late.logger.names()


SAY_ASKED = {"MOCHI_SAY_ASKED_WORDS": "true", "MODEL_API_KEY": "sk-test"}


async def _asking(model: FakeHintModel | None = None) -> Harness:
    harness = make_harness(env=SAY_ASKED, model=model, phrases=FakePhraseModel(SAID_FOR_HER))
    await harness.container.sessions.start()
    return harness


async def test_a_word_someone_asks_for_is_said_as_it_is_shown() -> None:
    # D-70: "como se diz X?" gets the word on the screen and in Mochi's voice, with no touch
    harness = await _asking()
    [home] = await harness.connect_all(HOME)
    outcome = await harness.say("How do you say guarda-chuva?")
    assert outcome.reply == "umbrella. umbrella."
    assert [e.payload.expression for e in home.events if isinstance(e.payload, Hint)] == [
        "umbrella"
    ]
    spoken = [e.payload for e in home.events if isinstance(e.payload, Speak)][-1]
    assert (spoken.text, spoken.language) == ("umbrella. umbrella.", Language.EN)
    await harness.container.pipeline.settle()
    assert _phrases(home) == []  # it was said already: no sentence is suggested after it


async def test_a_word_nobody_asked_for_and_a_question_to_a_colleague_stay_silent() -> None:
    harness = await _asking()
    assert (await harness.say("I need to adiar my meeting tomorrow.")).reply == ""  # a code switch
    harness.clock.advance(30)
    assert (await harness.say("Ben, como se diz recibo?")).reply == ""  # Ben was asked, by name
    quiet = make_harness()  # the switch off: as before
    await quiet.container.sessions.start()
    assert (await quiet.say("How do you say guarda-chuva?")).reply == ""


async def test_a_whole_sentence_someone_asks_for_is_said_once() -> None:
    answer = ModelSuggestion(
        decision="SHOW_HINT",
        reason=Reason.SAYS_UNKNOWN,
        expression="Vou terminar meu trabalho amanhã",
        meaning="I will finish my work tomorrow",
        confidence=0.9,
        expression_language="pt-BR",
        meaning_language="en",
    )
    harness = await _asking(FakeHintModel(answer))
    asked = 'Hum, how do I say in Portuguese, uh, "I will finish my work tomorrow"?'
    assert (await harness.say(asked)).reply == "Vou terminar meu trabalho amanhã."


async def test_no_sentence_when_there_is_nothing_to_say_or_it_is_switched_off() -> None:
    nothing, phrases = await _meeting(None)
    await _stuck(nothing)
    assert len(phrases.requests) == 1 and "phrase_suggested" not in nothing.logger.names()
    off_model = FakePhraseModel(SAID_FOR_HER)
    off = make_harness(env={"MOCHI_SUGGEST_PHRASES": "false"}, phrases=off_model)
    await off.container.sessions.start()
    await _stuck(off)
    assert off_model.requests == []
    plain, plain_model = await _meeting()
    await plain.say("Shall we start with the budget today?")  # no hint: nobody was stuck
    await plain.container.pipeline.settle()
    assert plain_model.requests == []


def _phraser(sentence: str | None = SAID_FOR_HER) -> tuple[Phraser, FakePhraseModel]:
    model = FakePhraseModel(sentence)
    return Phraser(model, Lexicon.load(), IntelligenceSettings()), model


async def test_a_sentence_is_suggested_only_for_someone_who_was_saying_something() -> None:
    phraser, model = _phraser()
    turn, hint = make_turn(STUCK), make_hint(0)
    assert await phraser.suggest(turn, make_context(), hint) == SAID_FOR_HER
    review = make_context(participants=[ANA], mode=SessionMode.REVIEW)
    assert await phraser.suggest(turn, review, hint) is None
    asked_mochi = hint.model_copy(update={"reason": Reason.ASKS_MOCHI})
    assert await phraser.suggest(turn, make_context(), asked_mochi) is None  # answered aloud
    assert await phraser.suggest(make_turn("the, um, adiar"), make_context(), hint) is None
    assert len(model.requests) == 1


def test_a_suggestion_that_does_not_hold_up_is_not_offered() -> None:
    phraser, _ = _phraser()
    asked = PhraseRequest(text=STUCK, recent_texts=[], language=Language.EN, word="postpone")
    good = PhraseAnswer(
        decision="SUGGEST", sentence="  Because we need to postpone\n the release. "
    )
    assert phraser.accepted(asked, good) == SAID_FOR_HER
    for doubtful in (
        None,
        PhraseAnswer(decision="IGNORE"),
        PhraseAnswer(decision="SUGGEST", sentence=""),
        PhraseAnswer(decision="SUGGEST", sentence=STUCK),  # what she said already
        PhraseAnswer(decision="SUGGEST", sentence="Postpone it."),  # not a sentence of hers
        PhraseAnswer(decision="SUGGEST", sentence="Porque a gente precisa adiar o lançamento."),
        PhraseAnswer(decision="SUGGEST", sentence="word " * 30),
    ):
        assert phraser.accepted(asked, doubtful) is None


async def test_the_openai_phrase_model_and_a_model_that_fails() -> None:
    http = FakeHttpClient(
        [_reply('{"decision": "SUGGEST", "sentence": "We need to unblock it."}'), _reply("nope")]
    )
    model = OpenAiPhraseModel(
        JsonChat(http, JsonChatConfig("https://llm/v1", "tiny", "k", 2.0), "phrase")
    )
    asked = PhraseRequest(
        text="We need to destravar it.",
        recent_texts=["Why?"],
        language=Language.EN,
        word="unblock",
        said="destravar",
    )
    answer = await model.phrase(asked)
    assert answer is not None and answer.sentence == "We need to unblock it."
    sent = http.posts[0].payload
    assert isinstance(sent, dict) and "destravar" in str(sent["messages"])
    assert await model.phrase(asked) is None and parse_phrase("[]") is None
    await model.warm_up()
    assert await NullPhraseModel().phrase(asked) is None

    class Broken(FakePhraseModel):
        async def phrase(self, request: PhraseRequest) -> PhraseAnswer | None:
            raise RuntimeError("boom")

    broken = Phraser(Broken(), Lexicon.load(), IntelligenceSettings())
    assert await broken.suggest(make_turn(STUCK), make_context(), make_hint(0)) is None
