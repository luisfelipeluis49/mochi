"""Phrases Mochi teaches become learning events (DECISIONS D-45)."""

from mochi_backend.intelligence.hint_builder import HintFactory
from mochi_backend.intelligence.saved_phrase import MAX_PHRASES, PhraseSaver, phrases_in
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import (
    Decision,
    DecisionKind,
    Language,
    Participant,
    SessionContext,
    SessionMode,
    Speak,
    SpeakReason,
)
from tests.fakes.fake_clock import FakeClock

ANA = Participant(
    user_id="ana", comfortable_languages=[Language.PT_BR], target_language=Language.EN
)
BEN = Participant(
    user_id="ben", comfortable_languages=[Language.EN], target_language=Language.PT_BR
)


def _language_of(text: str, fallback: Language) -> Language:
    return Language.PT_BR if "bom dia" in text else Language.EN if "morning" in text else fallback


def _saver() -> PhraseSaver:
    return PhraseSaver(HintFactory(FakeClock(), SequentialIdGenerator(), 8.0), _language_of)


def _context() -> SessionContext:
    return SessionContext(
        session_id="s",
        mode=SessionMode.TOGETHER,
        focus=Language.EN,
        participants=[ANA, BEN],
        recent_turns=[],
        recent_hints=[],
        activity=None,
        learning_events={"ana": [], "ben": []},
    )


def _says(text: str) -> Decision:
    speak = Speak(text=text, language=Language.EN, reason=SpeakReason.ASKS_MOCHI)
    return Decision(decision=DecisionKind.SPEAK, hint=None, speak=speak, learning_events=[])


def test_phrases_are_read_from_the_tag_and_capped() -> None:
    assert phrases_in("[phrase: good morning | bom dia] Try!") == [("good morning", "bom dia")]
    assert phrases_in("[Phrase : a b | c d ]") == [("a b", "c d")]
    assert phrases_in("[phrase: apartment | apartamento]") == [("apartment", "apartamento")]
    many = "".join(f"[phrase: p{i} | m{i}]" for i in range(5))
    assert len(phrases_in(many)) == MAX_PHRASES
    assert (
        phrases_in(
            "[phrase: one two three four five six seven eight nine ten eleven twelve thirteen | x]"
        )
        == []
    )
    assert phrases_in("[show umbrella] [mood happy] no phrase here") == []


def test_the_phrase_is_saved_for_the_person_learning_its_language() -> None:
    decision = _saver().add_to(_says("[phrase: good morning | bom dia] Say it!"), _context())
    [event] = decision.learning_events
    assert (event.user_id, event.expression, event.meaning) == ("ana", "good morning", "bom dia")
    assert event.target_language is Language.EN and event.hint_id is None


def test_a_phrase_in_the_other_language_goes_to_the_other_learner() -> None:
    decision = _saver().add_to(_says("[phrase: bom dia | good morning] Fala!"), _context())
    assert [e.user_id for e in decision.learning_events] == ["ben"]


def test_no_speech_no_tag_or_a_saved_phrase_changes_nothing() -> None:
    silent = Decision(decision=DecisionKind.IGNORE, hint=None, speak=None, learning_events=[])
    assert _saver().add_to(silent, _context()) == silent
    plain = _says("Just chatting.")
    assert _saver().add_to(plain, _context()) == plain
    first = _saver().add_to(_says("[phrase: good morning | bom dia]"), _context())
    known = _context().model_copy(update={"learning_events": {"ana": first.learning_events}})
    assert _saver().add_to(_says("[phrase: Good Morning | bom dia]"), known).learning_events == []
