"""An intelligence whose `decide` always fails, to prove one bad turn does not stop a session."""

from mochi_backend.intelligence.service import Intelligence
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_contracts import Decision, SessionContext, Turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.gated_intelligence import GatedIntelligence


class BrokenIntelligence(GatedIntelligence):
    """Implements `IntelligencePort`; everything but `decide` works as usual."""

    def __init__(self) -> None:
        brain = Intelligence(clock=FakeClock(), ids=SequentialIdGenerator(), model=FakeHintModel())
        super().__init__(brain)

    async def decide(self, turn: Turn, context: SessionContext) -> Decision:
        """Fail, as a bug or a broken model would."""
        raise RuntimeError("boom")
