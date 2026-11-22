"""A review: Mochi brings back one person's saved words, and saying one counts as recalled."""

import json

from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus, ReviewWord
from mochi_backend.intelligence.learning_rules import recalled_updates, words_to_review
from mochi_backend.intelligence.openai_character_model import messages_for, session_note
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.word_owner import owner_for
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import (
    DecisionKind,
    Language,
    LearningEvent,
    LearningState,
    Reason,
    SessionContext,
    SessionMode,
    StateChange,
)
from tests.factories import ANA, BEN, make_context, make_hint, make_turn
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel


def _card(word: str, state: LearningState = LearningState.DISCOVERED) -> LearningEvent:
    return LearningEvent(
        learning_event_id=f"learn_{word}",
        user_id="ana",
        target_language=Language.EN,
        expression=word,
        meaning=f"{word}-pt",
        detection_signal=Reason.CODE_SWITCH,
        hint_id=None,
        learning_state=state,
        state_history=[StateChange(learning_state=state, at="2026-11-18T10:00:00.000Z")],
    )


def _review(*cards: LearningEvent, mode: SessionMode = SessionMode.REVIEW) -> SessionContext:
    context = make_context(participants=[ANA], mode=mode)
    return context.model_copy(update={"learning_events": {"ana": list(cards)}})


def test_the_words_to_review_are_the_ones_not_recalled_yet() -> None:
    cards = [
        _card("umbrella", LearningState.REINFORCED),
        _card("postpone", LearningState.ASSISTED),
        _card("queue"),
    ]
    assert [e.expression for e in words_to_review(_review(*cards))] == ["postpone", "queue"]
    assert words_to_review(_review(*cards, mode=SessionMode.MEETING)) == []
    many = [_card(f"word{i}") for i in range(9)]
    assert len(words_to_review(_review(*many))) == 6


def test_a_saved_word_said_in_a_review_is_recalled() -> None:
    context = _review(_card("postpone"), _card("umbrella"))
    said = make_turn("Sure, we had to postpone the launch.")
    [recalled] = recalled_updates(said, context, FakeClock())
    assert (recalled.expression, recalled.learning_state) == ("postpone", LearningState.REINFORCED)
    assert [s.learning_state for s in recalled.state_history] == [
        LearningState.DISCOVERED,
        LearningState.REINFORCED,
    ]
    assert recalled_updates(make_turn("Nice weather today."), context, FakeClock()) == []


def test_reading_a_word_off_a_fresh_hint_is_not_recalling_it() -> None:
    shown = _review(_card("postpone")).model_copy(update={"recent_hints": [make_hint(0)]})
    assert recalled_updates(make_turn("Ah, postpone!"), shown, FakeClock()) == []


def test_nothing_is_recalled_in_a_meeting() -> None:
    meeting = _review(_card("postpone"), mode=SessionMode.MEETING)
    assert recalled_updates(make_turn("Let's postpone it."), meeting, FakeClock()) == []


def test_the_recognised_speaker_owns_the_word_when_several_people_learn_the_language() -> None:
    caio = ANA.model_copy(update={"user_id": "caio"})
    meeting = make_context(participants=[ANA, caio, BEN])
    assert owner_for(meeting) is None  # two people are learning English: nobody in particular
    assert owner_for(meeting, "caio") == "caio"
    assert owner_for(meeting, "stranger") is None  # a voice that is not in the meeting
    assert owner_for(meeting, "ben") is None  # Ben is not learning English: not believed
    assert owner_for(make_context(), None) == "ana"  # two people: the old rule still holds
    # the device reports a voice when it changes, so "ben" can be a moment stale: Ana's word
    assert owner_for(make_context(), "ben") == "ana"
    portuguese = make_context().model_copy(update={"focus": Language.PT_BR})
    assert owner_for(portuguese, "ben") == "ben" and owner_for(portuguese, "ana") == "ben"


def test_in_a_review_every_word_is_the_reviewers_whichever_language_they_ask_in() -> None:
    review = make_context(participants=[ANA], mode=SessionMode.REVIEW)
    asked_in_portuguese = review.model_copy(update={"focus": Language.PT_BR})
    assert owner_for(review) == "ana" and owner_for(asked_in_portuguese) == "ana"
    alone_in_a_meeting = make_context(participants=[ANA]).model_copy(
        update={"focus": Language.PT_BR}
    )
    assert owner_for(alone_in_a_meeting) is None  # a meeting keeps the learner rule


async def test_a_hint_goes_to_the_person_whose_voice_said_the_sentence() -> None:
    caio = ANA.model_copy(update={"user_id": "caio"})
    meeting = make_context(participants=[ANA, caio, BEN])
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel())
    turn = make_turn("I need to adiar my meeting tomorrow.")
    unknown = await brain.decide(turn, meeting)
    assert unknown.hint is not None and unknown.hint.target_user_id is None
    assert unknown.learning_events[0].user_id is None
    heard = await brain.decide(turn.model_copy(update={"speaker_user_id": "caio"}), meeting)
    assert heard.hint is not None and heard.hint.target_user_id == "caio"
    assert heard.learning_events[0].user_id == "caio"


async def test_in_a_review_mochi_is_told_the_words_and_the_card_moves_on() -> None:
    mochi = FakeCharacterModel("[mood proud] Postpone, yes! Now use it about your week.")
    brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel())
    brain.speak_as(mochi)
    brain.session_started(conversing=True, language=Language.PT_BR)
    context = _review(_card("postpone"), _card("umbrella", LearningState.REINFORCED))
    decision = await brain.decide(make_turn("I think it was postpone?"), context)
    assert decision.decision is DecisionKind.SPEAK
    request = mochi.requests[0]
    assert request.reviewing and request.conversing
    assert request.review == [ReviewWord(expression="postpone", meaning="postpone-pt")]
    assert [e.learning_state for e in decision.learning_events] == [LearningState.REINFORCED]


def test_mochi_is_told_which_kind_of_session_it_is_in() -> None:
    base = CharacterRequest(text="Oi", history=[], status=DeviceStatus())
    assert "This session is a meeting" in session_note(base)
    empty = base.model_copy(update={"reviewing": True})
    assert "no saved words to go over yet" in session_note(empty)
    words = [ReviewWord(expression="postpone", meaning="adiar"), ReviewWord(expression="queue")]
    review = empty.model_copy(update={"review": words})
    note = session_note(review)
    assert "postpone (adiar); queue (no translation)" in note and "review" in note
    assert note in json.dumps(messages_for(review, "PROMPT"), ensure_ascii=False)
