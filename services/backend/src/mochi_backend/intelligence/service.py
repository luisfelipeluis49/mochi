"""The intelligence object the gateway uses through its port: decide, handle, apply, words_for."""

from mochi_backend.intelligence.decision_flow import DecisionFlow
from mochi_backend.intelligence.hint_builder import HintFactory
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.intelligence.model_port import HintModel
from mochi_backend.intelligence.round_engine import RoundEngine
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.clock import Clock
from mochi_backend.platform.ids import IdGenerator
from mochi_contracts import (
    ActivityCommand,
    ActivityResult,
    Decision,
    LearningEvent,
    SessionContext,
    Turn,
)


class Intelligence:
    """AGENTS 6.5 as an object, so clock, ids and model are injected (no module singletons)."""

    def __init__(
        self,
        *,
        clock: Clock,
        ids: IdGenerator,
        model: HintModel,
        lexicon: Lexicon | None = None,
        settings: IntelligenceSettings | None = None,
    ) -> None:
        book = lexicon or Lexicon.load()
        tuning = settings or IntelligenceSettings()
        factory = HintFactory(clock, ids, tuning.hint_ttl_seconds)
        self._memory = MemoryStore()
        self._rounds = RoundEngine(clock, ids, book)
        self._flow = DecisionFlow(
            clock=clock,
            factory=factory,
            lexicon=book,
            model=model,
            settings=tuning,
        )

    async def decide(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide what Mochi does with one turn. Example: "I need to adiar my meeting" -> hint."""
        return await self._flow.run(turn, context)

    def handle(self, command: ActivityCommand, context: SessionContext) -> ActivityResult:
        """Start a round or record its result. Raises ValueError when the command cannot apply."""
        return self._rounds.handle(command, context)

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or update learning events; returns the stored records."""
        return self._memory.apply(proposals)

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """One person's saved words, newest first."""
        return self._memory.words_for(user_id)

    def reset(self) -> None:
        """Clear saved words and any unfinished round (demo reset)."""
        self._memory.reset()
        self._rounds.reset()
