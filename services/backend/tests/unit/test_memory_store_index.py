"""`MemoryStore.words_for` keeps its order and its owners while it reads from an index."""

from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_contracts import Language, LearningEvent, LearningState, StateChange
from tests.harness import make_harness


def _word(event_id: str, user: str | None, expression: str = "x") -> LearningEvent:
    return LearningEvent(
        learning_event_id=event_id,
        user_id=user,
        target_language=Language.EN,
        expression=expression,
        meaning=None,
        detection_signal="code_switch",
        hint_id=None,
        learning_state=LearningState.DISCOVERED,
        state_history=[
            StateChange(learning_state=LearningState.DISCOVERED, at="2026-11-22T10:00:00.000Z")
        ],
    )


def test_words_are_newest_first_per_person_and_nobodys_belong_to_nobody() -> None:
    store = MemoryStore([_word("a", "ana"), _word("b", "ben")])
    store.apply([_word("c", "ana"), _word("d", None)])
    assert [e.learning_event_id for e in store.words_for("ana")] == ["c", "a"]
    assert [e.learning_event_id for e in store.words_for("ben")] == ["b"]
    assert store.words_for("nobody") == []


def test_replacing_an_event_keeps_its_place_and_moving_it_moves_its_owner() -> None:
    store = MemoryStore([_word("a", "ana"), _word("b", "ana")])
    store.apply([_word("a", "ana", "changed")])
    assert [e.expression for e in store.words_for("ana")] == ["x", "changed"]
    store.apply([_word("a", "ben")])
    assert [e.learning_event_id for e in store.words_for("ana")] == ["b"]
    assert [e.learning_event_id for e in store.words_for("ben")] == ["a"]


def test_reset_forgets_every_index() -> None:
    store = MemoryStore([_word("a", "ana")])
    store.reset()
    assert store.words_for("ana") == []


async def test_the_team_view_added_up_in_a_thread_equals_the_one_on_the_loop() -> None:
    service = make_harness().container.team_service
    assert await service.insights_in_thread("demo", "ana", 30) == service.insights(
        "demo", "ana", 30
    )
