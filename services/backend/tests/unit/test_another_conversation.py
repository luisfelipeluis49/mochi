"""One conversation per session over the same saved words."""

from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.harness import Harness, make_harness


def test_words_saved_in_one_conversation_are_read_in_the_other() -> None:
    clock, ids = FakeClock(), SequentialIdGenerator()
    first = Intelligence(clock=clock, ids=ids, model=FakeHintModel())
    second = first.another_conversation()
    assert second is not first
    assert second.words_for("ana") == first.words_for("ana") == []


async def test_a_word_saved_through_one_session_is_in_the_other_sessions_brain() -> None:
    harness: Harness = make_harness()
    await harness.container.sessions.start()
    phone = harness.container.registry.open("p-1")
    await phone.sessions.start()
    await phone.pipeline.handle_turn("I need to adiar my meeting tomorrow.")
    assert phone.core.intelligence is not harness.container.core.intelligence
    assert harness.container.core.intelligence.words_for("ana")[0].expression == "postpone"
