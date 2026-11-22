"""The intelligence object the gateway uses through its port: decide, handle, apply, words_for."""

import asyncio

from mochi_backend.intelligence.character_port import (
    CharacterModel,
    DeviceStatus,
    NullCharacterModel,
)
from mochi_backend.intelligence.decision_flow import DecisionFlow, Minds
from mochi_backend.intelligence.hint_builder import HintFactory
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.intelligence.mochi_talk import MochiTalk
from mochi_backend.intelligence.model_port import HintModel
from mochi_backend.intelligence.round_engine import RoundEngine
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.warm_start import WarmsUp
from mochi_backend.platform.clock import Clock
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.text_sink import TextSink
from mochi_contracts import (
    ActivityCommand,
    ActivityResult,
    Decision,
    Language,
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
        self._thinkers: list[HintModel | CharacterModel] = [model]
        self._warming: set[asyncio.Task[None]] = set()  # kept, or a running task may be collected
        self._rounds = RoundEngine(clock, ids, book)
        self._talk = MochiTalk(clock, NullCharacterModel(), tuning)
        self._flow = DecisionFlow(
            clock=clock,
            factory=factory,
            lexicon=book,
            minds=Minds(model, self._talk),
            settings=tuning,
        )

    async def decide(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide what Mochi does with one turn. Example: "I need to adiar my meeting" -> hint."""
        return await self._flow.run(turn, context)

    async def decide_streaming(
        self, turn: Turn, context: SessionContext, sink: TextSink
    ) -> Decision:
        """`decide`, but a free-chat line goes to `sink` while it is written (D-37).

        The Decision is the same as `decide` would return. Example: `decide_streaming(t, c, s)`.
        """
        return await self._flow.run(turn, context, sink)

    def handle(self, command: ActivityCommand, context: SessionContext) -> ActivityResult:
        """Start a round or record its result. Raises ValueError when the command cannot apply."""
        return self._rounds.handle(command, context)

    def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
        """Create or update learning events; returns the stored records."""
        return self._memory.apply(proposals)

    def words_for(self, user_id: str) -> list[LearningEvent]:
        """One person's saved words, newest first."""
        return self._memory.words_for(user_id)

    def keep_words_in(self, memory: MemoryStore) -> None:
        """Use this store for saved words (one that holds the words kept before a restart).

        Example: `brain.keep_words_in(MemoryStore(kept_events, sink))`.
        """
        self._memory = memory

    def speak_as(self, character: CharacterModel) -> None:
        """Give Mochi the model that writes its lines (without one it keeps its fixed lines).

        Example: `brain.speak_as(OpenAiCharacterModel(http, url, "gpt-4.1-mini", key, 6.0))`.
        """
        self._talk.use(character)
        self._thinkers = [self._thinkers[0], character]

    def session_started(self, woken: bool, language: Language | None = None) -> None:
        """A session begins. `woken`: someone called Mochi on the device (its wake phrase) to talk
        to it, so the next sentence is for it. Otherwise Mochi waits for its name.

        `language`: the one Mochi was called and greeted in; a short answer that could be either
        language ("Play.", "Ok.") is then answered in it.
        Example: `session_started(True, Language.PT_BR)`.
        """
        self._talk.begin(woken, language)
        self._warm_up()

    def _warm_up(self) -> None:
        """Open the models' connections now: the first sentence should not wait for them (D-41)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # called outside a loop (a script, a plain test): nothing to hurry
            return
        for thinker in self._thinkers:
            if isinstance(thinker, WarmsUp):
                task = loop.create_task(thinker.warm_up())
                self._warming.add(task)
                task.add_done_callback(self._warming.discard)

    def device_status(
        self, volume: int | None, temperature: int | None, voices: list[str], speaker: str | None
    ) -> None:
        """What the device reports about itself; Mochi can talk about it.

        Example: `device_status(80, 52, ["Ana"], "Ana")`.
        """
        self._talk.status = DeviceStatus(
            volume=volume, temperature=temperature, voices=voices, speaker=speaker
        )

    def reset(self) -> None:
        """Clear saved words, any unfinished round and Mochi's conversation (demo reset)."""
        self._memory.reset()
        self._rounds.reset()
        self._talk.reset()
