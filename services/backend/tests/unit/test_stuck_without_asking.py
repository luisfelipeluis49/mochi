"""Someone who is stuck and does not ask: the signs in the sentence, and what is done with them.

Measured on sentences written the way the speech recogniser writes them (DECISIONS D-42): before
this, a hint came for 12 of 63 such sentences.
"""

import json

import pytest

from mochi_backend.intelligence.answer_checks import same_family
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion, Suspect
from mochi_backend.intelligence.openai_hint_model import (
    SUSPECT_NOTE,
    SYSTEM_PROMPT,
    OpenAiHintModel,
)
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.stuck_signs import (
    StuckSign,
    describes,
    partner_lost,
    searches,
    searching_aside,
    starts_over,
    stops_short,
    stuck_signs,
)
from mochi_backend.intelligence.subtle_cases import suspect_in
from mochi_backend.platform.http_client import HttpResponse
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, DecisionKind, Language, Reason, SessionContext
from tests.factories import make_context, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_http_client import FakeHttpClient

EN, PT = Language.EN, Language.PT_BR
LEXICON = Lexicon.load()


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("It's raining a lot and I forgot my", EN),
        ("I can't open the door because I lost my.", EN),
        ("I need to cut this paper. Do you have a...", EN),
        ("My phone is almost dead, can I borrow your, um", EN),
        ("I cut my finger, do you have a?", EN),
        ("I couldn't sleep because my neighbors were making a lot of.", EN),
        ("I want to eat the, hmm, the green vegetable, small trees.", EN),
        ("Está chovendo muito e eu esqueci o meu", PT),
        ("Eu quero abrir o vinho, mas não tenho o.", PT),
        ("Estou com frio, vou pegar o meu, hum", PT),
        ("Você me passa a", PT),  # the feminine article, and the contracted ones
        ("Eu fui ao", PT),
    ],
)
def test_a_sentence_that_stops_where_a_word_should_follow(text: str, language: Language) -> None:
    assert stops_short(text, language)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("I forgot my keys again.", EN),
        ("Who are you going with?", EN),  # a finished question may end on a preposition
        ("I don't want to.", EN),
        ("I told her.", EN),
        ("Uh, yes, no, I mean, maybe tomorrow.", EN),  # "no" is Portuguese "in the", not here
        ("So, um, yesterday I went to the beach with my friends.", EN),
        ("Hmm.", EN),
        ("Eu vou, eu vou sim, pode deixar.", PT),
        ("Você falou o quê?", PT),
        ("Eu gosto muito.", PT),
        ("Hoje eu comi muito, hum, foi bom.", PT),
        ("That's the one I told you about.", EN),  # English ends on its prepositions
        ("This is what I was looking for.", EN),
    ],
)
def test_a_finished_sentence_does_not_stop_short(text: str, language: Language) -> None:
    assert not stops_short(text, language)


def test_starting_the_sentence_again_and_again() -> None:
    assert starts_over("We should, we need to, we have to make the meeting later.")
    assert starts_over("She is very. She is. She doesn't like to spend money.")
    assert starts_over("Eu quero, eu preciso, eu vou fazer a reunião mais tarde.")
    assert not starts_over("I like the, the blue one.")  # once is how everybody talks
    assert not starts_over("I, I, I can't believe it!")  # emphasis
    assert not starts_over("We need to, no wait, we already did that.")  # a correction
    assert not starts_over("We went to Rio, we went to Bahia, we went to Recife.")  # a list
    assert not starts_over("I went home, I ate dinner, I watched a long movie.")  # a story


def test_a_general_word_with_what_the_thing_does() -> None:
    assert describes("I went to the place where you buy medicine.")
    assert describes("He is the doctor for the teeth.")
    assert describes("Me passa o negócio de cortar papel.")
    assert not describes("The thing is, I don't really like horror movies.")
    assert not describes("I like this place a lot.")
    # also true of sentences where nobody is stuck: a clue for the model, never a verdict
    assert describes("It's the place where I grew up.")


def test_looking_for_the_word_aloud() -> None:
    assert searches("It's cold, I need my, como é que fala, my...")
    assert searches("A gente precisa comprar, como se chama, pra limpar os dentes.")
    assert not searches("I don't remember his name.")
    assert searching_aside("Eu preciso do, how do you say, para abrir a porta.", PT)
    assert not searching_aside("How do you say fork in Portuguese?", EN)  # a question, no aside


def test_a_listener_who_did_not_understand() -> None:
    assert partner_lost("Sorry, a what?", None)
    assert partner_lost("Your what?", "Can you lend me your grampeador?")
    assert partner_lost("Como assim?", None)
    assert partner_lost("The place of the books?", "I went to the place of the books to study.")
    assert not partner_lost("Sorry, what did you say? It's loud in here.", None)
    assert not partner_lost("Do you like books?", "I went to the place of the books to study.")
    assert not partner_lost("What time is it?", None)


def test_every_sign_in_one_sentence() -> None:
    text = "It's cold, I need my, como é que fala, my..."
    assert stuck_signs(text, None, EN) == [StuckSign.STOPS_SHORT, StuckSign.SEARCHES]
    assert stuck_signs("I think we should go now.", None, EN) == []


def _open(reason: str, expression: str, **more: object) -> ModelSuggestion:
    fields = {"decision": "SHOW_HINT", "reason": reason, "expression": expression}
    return ModelSuggestion.model_validate({**fields, "confidence": 0.9, **more})


async def _decided(
    model: FakeHintModel, text: str, context: SessionContext | None = None
) -> Decision:
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=model)
    return await brain.decide(make_turn(text, 60), context or make_context())


async def test_the_model_is_told_what_was_noticed() -> None:
    model = FakeHintModel(_open("trails_off", "hands", meaning="mãos"))
    decision = await _decided(model, "Before we eat, I need to wash my")
    assert decision.hint is not None and decision.hint.expression == "hands"
    assert model.requests[0].noticed == ["stops_short"]


async def test_trailing_off_is_not_read_into_a_finished_sentence() -> None:
    """The model names the reason; whether the sentence stops short can be checked."""
    model = FakeHintModel(_open("trails_off", "umbrella", meaning="guarda-chuva"))
    decision = await _decided(model, "I think it is going to rain later today.")
    assert decision.decision is DecisionKind.IGNORE


async def test_restarts_and_not_understood_need_their_sign_too() -> None:
    restarts = FakeHintModel(_open("restarts", "postpone", meaning="adiar"))
    assert (await _decided(restarts, "We have to make the meeting later.")).hint is None
    again = "We should, we need to, we have to make the meeting later."
    assert (await _decided(restarts, again)).hint is not None
    lost = FakeHintModel(_open("not_understood", "library", meaning="biblioteca"))
    assert (await _decided(lost, "I like that place a lot.")).hint is None
    before = make_context(turns=[make_turn("I went to the place of the books.", 50)])
    longer = "Sorry, what did you mean by the place of the books?"  # the older marker's wording
    assert (await _decided(lost, longer, before)).hint is not None


async def test_two_words_from_a_lost_listener_are_enough_to_look() -> None:
    """ "Your what?" is under the three words a sentence needs, and still worth a look."""
    before = make_context(turns=[make_turn("Can you lend me your grampeador?", 50)])
    answer = _open("not_understood", "stapler", meaning="grampeador", expression_language="en")
    model = FakeHintModel(answer)
    decision = await _decided(model, "Your what?", before)
    assert decision.hint is not None and decision.hint.expression == "stapler"
    assert model.requests[0].noticed == ["partner_lost"]
    alone = FakeHintModel(answer)
    await _decided(alone, "Your what?")  # nothing was said before it: nothing to look at
    assert alone.requests == []


async def test_words_repeated_as_a_question_are_not_someone_trying_a_word_out() -> None:
    """ "The place of the books?" is all of the turn and was just said: by the OTHER person."""
    said = "Yesterday I went to the place of the books to study."
    answer = _open("not_understood", "library", meaning="the place of the books")
    echoed = await _decided(
        FakeHintModel(answer), "The place of the books?", make_context(turns=[make_turn(said, 50)])
    )
    assert echoed.hint is not None and echoed.hint.expression == "library"
    other = _open("not_understood", "biblioteca", meaning="library", expression_language="pt-BR")
    wrong = await _decided(
        FakeHintModel(other), "The place of the books?", make_context(turns=[make_turn(said, 50)])
    )
    assert wrong.hint is None  # the sentence that was not understood was English


async def test_a_listener_who_did_not_hear_is_not_shown_a_word_the_speaker_had() -> None:
    before = make_context(turns=[make_turn("Do you want to go to the beach tomorrow?", 50)])
    answer = _open("not_understood", "beach", meaning="praia", expression_language="en")
    decision = await _decided(FakeHintModel(answer), "Sorry, what?", before)
    assert decision.decision is DecisionKind.IGNORE


async def test_the_lost_listeners_language_does_not_decide_the_hints() -> None:
    """ "O quê?" is Portuguese; the word the other person needed was in their English."""
    before = make_context(turns=[make_turn("I need to buy a new tomada for my room.", 50)])
    answer = _open("not_understood", "outlet", meaning="tomada", expression_language="en")
    decision = await _decided(FakeHintModel(answer), "Desculpa, o quê? Não entendi.", before)
    assert decision.hint is not None
    assert decision.hint.target_language is EN and decision.hint.target_user_id == "ana"


async def test_a_hint_repeated_as_its_own_meaning_is_kept_without_a_meaning() -> None:
    answer = _open("trails_off", "casaco", meaning="casaco", expression_language="pt-BR")
    decision = await _decided(FakeHintModel(answer), "Estou com frio, vou pegar o meu, hum")
    assert decision.hint is not None
    assert decision.hint.expression == "casaco" and decision.hint.meaning is None


async def test_the_question_itself_is_never_the_word() -> None:
    answer = _open("says_unknown", "How do you say", meaning="Como se fala")
    decision = await _decided(FakeHintModel(answer), "Futs Como se fala Como se fala...")
    assert decision.decision is DecisionKind.IGNORE


async def test_an_aside_is_a_search_and_not_a_question_about_what_follows() -> None:
    answer = _open("trails_off", "chave", meaning="key", expression_language="pt-BR")
    model = FakeHintModel(answer)
    decision = await _decided(model, "Eu preciso do, how do you say, para abrir a porta.")
    assert model.requests[0].asked_about is None  # not "para abrir a porta"
    assert "searches" in model.requests[0].noticed
    assert decision.hint is not None and decision.hint.target_language is PT
    english = _open("says_unknown", "key", meaning="chave", expression_language="en")
    wrong = await _decided(FakeHintModel(english), "Eu preciso do, how do you say, a porta.")
    assert wrong.decision is DecisionKind.IGNORE  # the sentence is Portuguese: so is its word


def test_a_word_in_another_form_is_the_same_word() -> None:
    assert same_family("watched", "watch") and same_family("Animada", "animado")
    assert not same_family("plan", "intend") and not same_family("", "watch")


@pytest.mark.parametrize(
    ("text", "language", "meant"),
    [
        ("Yesterday I assisted a very good movie.", EN, "watch"),
        ("She is very sensible, she cries with every movie.", EN, "sensitive"),
        ("He works in a fabric of cars.", EN, "factory"),
        ("I need to go to the library to buy a new book.", EN, "bookstore"),
        ("Eu estou muito excitado com a viagem.", PT, "animado"),
    ],
)
def test_the_lexicon_suspects_a_false_friend(text: str, language: Language, meant: str) -> None:
    suspect = suspect_in(text, LEXICON, language)
    assert suspect is not None and suspect.meant == meant


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("He assisted the doctor during the surgery.", EN),
        ("This fabric is very soft.", EN),
        ("He's a sensible guy, I trust him.", EN),  # a model confirmed this one 4 times in 6
        ("I went to the library to buy a ticket for the concert.", EN),
        ("I went to the library to study for my exam.", EN),
        ("Eu pretendo viajar em julho.", PT),  # "pretender" means intend: correct
        ("I am excited about the trip.", PT),  # the Portuguese list is for Portuguese
        ("Eu estou muito excitado com a viagem.", EN),
    ],
)
def test_the_lexicon_suspects_nothing_in_ordinary_use(text: str, language: Language) -> None:
    assert suspect_in(text, LEXICON, language) is None


ASSISTED = "Yesterday I assisted a very good movie."


async def test_a_suspected_false_friend_is_put_to_the_model_and_confirmed() -> None:
    """Asked without the suspicion, the model had to name the same word unprompted, and
    "I pretend to travel in July." went unanswered (D-42)."""
    recast = "Yesterday I watched a very good movie."
    model = FakeHintModel(_open("look_alike", "watched", meaning="assistir", example=recast))
    decision = await _decided(model, ASSISTED)
    assert model.requests[0].suspect == Suspect(used="assist", meant="watch", look_alike="assistir")
    hint = decision.hint
    assert hint is not None and hint.reason is Reason.LOOK_ALIKE
    assert hint.expression == "watch" and hint.example == recast  # their own sentence, put right


async def test_a_suspicion_the_model_does_not_share_shows_nothing() -> None:
    sensible = "She is sensible, she never cries about small things."  # suspected, and correct
    assert (
        await _decided(FakeHintModel(ModelSuggestion(decision="IGNORE")), sensible)
    ).hint is None
    other = FakeHintModel(_open("look_alike", "reasonable", meaning="sensato"))
    assert (await _decided(other, sensible)).hint is None  # not the word the rule suspected


async def test_a_false_friend_is_left_to_mochis_own_reply_while_someone_talks_with_it() -> None:
    """A silent hint races Mochi's spoken reply, and when it wins Mochi says nothing (D-40)."""
    model = FakeHintModel(_open("look_alike", "watch", meaning="assistir"))
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=model)
    brain.session_started(True)
    decision = await brain.decide(make_turn(ASSISTED, 60), make_context())
    assert decision.hint is None and model.requests == []


async def test_a_described_word_that_was_said_is_not_missing() -> None:
    """The lexicon's cues ("they give", "when you pay") found receipt in a sentence that has it."""
    said = "When you pay, they always give you a receipt."
    assert (await _decided(FakeHintModel(None), said)).decision is DecisionKind.IGNORE
    described = "It's the paper they give you when you pay."
    assert (await _decided(FakeHintModel(None), described)).hint is not None


async def test_the_real_adapter_sends_the_signs_and_the_suspicion() -> None:
    body = json.dumps({"choices": [{"message": {"content": '{"decision": "IGNORE"}'}}]})
    http = FakeHttpClient([HttpResponse(200, body), HttpResponse(200, body)])
    model = OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0)
    suspect = Suspect(used="assist", meant="watch", look_alike="assistir")
    plain = ModelRequest(text="Hello there.", recent_texts=[], focus=EN, candidate_reasons=[])
    marked = plain.model_copy(update={"noticed": ["stops_short"], "suspect": suspect})
    await model.suggest(plain)
    await model.suggest(marked)
    first, second = (_user_json(post.payload) for post in http.posts)
    assert "noticed" not in first and "suspect" not in first
    assert second["noticed"] == ["stops_short"]
    assert second["suspect"] == {"used": "assist", "meant": "watch", "look_alike": "assistir"}
    plain_roles, marked_roles = (_roles(post.payload) for post in http.posts)
    assert plain_roles == ["system", "user"]  # how to judge a false friend is not sent...
    assert marked_roles == ["system", "system", "user"]  # ...unless one is suspected


async def test_a_suspected_false_friend_gets_a_moment_of_thought_and_nothing_else_does() -> None:
    """Answering at once, the model confirmed "sensible" for someone who never cries (D-42)."""
    body = json.dumps({"choices": [{"message": {"content": '{"decision": "IGNORE"}'}}]})
    http = FakeHttpClient([HttpResponse(200, body)] * 3)
    suspect = Suspect(used="assist", meant="watch", look_alike="assistir")
    plain = ModelRequest(text="Hello there.", recent_texts=[], focus=EN, candidate_reasons=[])
    marked = plain.model_copy(update={"suspect": suspect})
    fast = OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0).thinking("none")
    await fast.suggest(plain)
    await fast.suggest(marked)
    await OpenAiHintModel(http, "https://llm.example/v1", "m", "k", 2.0).suggest(marked)
    sent = [post.payload for post in http.posts]
    assert all(isinstance(payload, dict) for payload in sent)
    efforts = [payload.get("reasoning_effort") for payload in sent if isinstance(payload, dict)]
    assert efforts == ["none", "low", None]  # a model without the setting is asked as before


def _roles(payload: object) -> list[object]:
    assert isinstance(payload, dict) and isinstance(payload["messages"], list)
    return [message["role"] for message in payload["messages"]]


def _user_json(payload: object) -> dict[str, object]:
    assert isinstance(payload, dict)
    messages = payload["messages"]
    assert isinstance(messages, list) and isinstance(messages[-1], dict)
    loaded = json.loads(messages[-1]["content"])
    assert isinstance(loaded, dict)
    return loaded


def test_the_instructions_explain_every_sign_they_may_be_sent() -> None:
    for sign in StuckSign:
        assert f"- {sign.value}:" in SYSTEM_PROMPT
    assert "`suspect`" in SYSTEM_PROMPT and "look_alike" in SUSPECT_NOTE
    # the note's example sentences are kept out of the standing instructions: there they drew
    # the model to a false friend two sentences back instead of the sentence it was judging
    assert "assisted" not in SYSTEM_PROMPT and "pretend" not in SYSTEM_PROMPT
