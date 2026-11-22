"""The intelligence object the gateway uses through its port: decide, apply, words_for."""

import asyncio

from mochi_backend.intelligence import speech_report
from mochi_backend.intelligence.character_port import (
    CharacterModel,
    DeviceStatus,
    NullCharacterModel,
)
from mochi_backend.intelligence.coach_port import CoachModel, NullCoachModel
from mochi_backend.intelligence.decision_flow import DecisionFlow, Minds
from mochi_backend.intelligence.explain_port import ExplainModel, NullExplainModel
from mochi_backend.intelligence.explaining import Explainer
from mochi_backend.intelligence.hint_builder import HintFactory
from mochi_backend.intelligence.learning_rules import used_alone
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.intelligence.mochi_talk import MochiTalk
from mochi_backend.intelligence.model_port import HintModel
from mochi_backend.intelligence.phrase_port import NullPhraseModel, PhraseModel
from mochi_backend.intelligence.phrasing import Phraser
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.warm_start import WarmsUp
from mochi_backend.platform.clock import Clock, iso_z, parse_iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.text_sink import TextSink
from mochi_contracts import (
    ConversationReport,
    Decision,
    Hint,
    Language,
    LearningEvent,
    Participant,
    SessionContext,
    TranscriptMark,
    Turn,
    Utterance,
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
        self._parts = (clock, ids, model, book, tuning)
        factory = HintFactory(clock, ids, tuning.hint_ttl_seconds)
        self._memory = MemoryStore()
        self._thinkers: list[HintModel | CharacterModel | ExplainModel] = [model]
        self._explains: ExplainModel = NullExplainModel()
        self._explainer = Explainer(self._explains, book, clock, tuning)
        self._phrases: PhraseModel = NullPhraseModel()
        self._phraser = Phraser(self._phrases, book, tuning)
        self._coach: CoachModel = NullCoachModel()
        self._warming: set[asyncio.Task[None]] = set()  # kept, or a running task may be collected
        self._talk = MochiTalk(clock, NullCharacterModel(), tuning)
        self._flow = DecisionFlow(
            clock=clock,
            factory=factory,
            lexicon=book,
            minds=Minds(model, self._talk),
            settings=tuning,
        )

    def another_conversation(self) -> "Intelligence":
        """A fresh conversation (own Mochi talk and device status) over the same words.

        Each session has one, so a phone's chat never changes the Pi's; the saved words are the
        one thing they share. Example: `brain.another_conversation().words_for("ana")` is the same
        list as `brain.words_for("ana")`.
        """
        clock, ids, model, book, tuning = self._parts
        other = Intelligence(clock=clock, ids=ids, model=model, lexicon=book, settings=tuning)
        other._memory = self._memory  # noqa: SLF001 - the same class sharing its saved words
        other._talk.use(self._talk.character)  # noqa: SLF001
        other.explain_with(self._explains)
        other.coach_with(self._coach)
        other.phrase_with(self._phrases)
        return other

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
        self._thinkers = [self._thinkers[0], character, self._explains]

    def explain_with(self, model: ExplainModel) -> None:
        """Give Mochi the model that explains idioms and technical terms (without one, none are).

        Example: `brain.explain_with(OpenAiExplainModel(JsonChat(http, config, "explain")))`.
        """
        self._explains = model
        self._explainer.use(model)
        self._thinkers = [*self._thinkers[:2], model]

    def phrase_with(self, model: PhraseModel) -> None:
        """Give Mochi the model that writes the sentence a stuck speaker was reaching for (D-59).

        Example: `brain.phrase_with(OpenAiPhraseModel(JsonChat(http, config, "phrase")))`.
        """
        self._phrases = model
        self._phraser.use(model)

    async def suggest(self, turn: Turn, context: SessionContext, hint: Hint) -> str | None:
        """The whole sentence the speaker of `turn` was trying to say, after `hint` gave them the
        word (one-touch assistance, D-59); None when there is nothing to say for them.

        Example: "Because we need to, como é que fala, destravar a autenticação." ->
        "Because we need to unblock the authentication process."
        """
        return await self._phraser.suggest(turn, context, hint)

    def coach_with(self, model: CoachModel) -> None:
        """Give Mochi the model that looks over a person's sentences after a session.

        Example: `brain.coach_with(OpenAiCoachModel(JsonChat(http, config, "coach")))`.
        """
        self._coach = model

    async def coach(
        self, draft: ConversationReport, person: Participant
    ) -> ConversationReport | None:
        """The report with what was wrong in that person's sentences filled in (D-54).

        `draft` holds their sentences and the words they needed. None when there is no model or
        it did not answer. Example: `await brain.coach(draft, ana)`.
        """
        return await speech_report.completed(self._coach, draft, person, self._parts[3])

    async def explain(self, turn: Turn, context: SessionContext) -> TranscriptMark | None:
        """An idiom or a technical term in the sentence that the people listening may not
        know, with what it means (D-53); None for nearly every sentence, and always while
        someone is talking WITH Mochi. Example: "Let's circle back on that." -> "circle back".
        """
        if self._talk.attentive or self._talk.listening() or self._talk.explains:
            return None  # ... and a web session's quiet listener explains aloud itself (D-62)
        return await self._explainer.explain(turn, context)

    def used_alone(
        self, said: list[Utterance], shown: list[str], began: str
    ) -> list[LearningEvent]:
        """After a meeting: the saved words people used in it on their own, as proposals for
        `apply` (D-55). `said`: the meeting's sentences with their final speakers; `shown`: every
        word a screen showed during it; `began`: when it started.

        Example: `brain.apply(brain.used_alone(said, ["postpone"], record.started_at))`.
        """
        on_screen = {word.lower() for word in shown}
        now, start = iso_z(self._parts[0].now()), parse_iso_z(began)
        people = sorted({sentence.user_id for sentence in said if sentence.user_id})
        return [
            event
            for person in people
            for event in used_alone(self.words_for(person), said, on_screen, start, now)
        ]

    def session_started(
        self, conversing: bool, language: Language | None = None, explains: bool = False
    ) -> None:
        """A session begins. `conversing`: one person talks WITH Mochi (a review on their phone),
        so every sentence is for it. Otherwise it is a meeting and Mochi waits for its name.

        `language`: the one Mochi was called and greeted in; a short answer that could be either
        language ("Ok.") is then answered in it.
        `explains`: while it only listens, Mochi may also explain an idiom or a wrong expression
        aloud, unasked (a web session's quiet mode, D-62).
        Example: `session_started(True, Language.PT_BR)`.
        """
        self._talk.begin(conversing, language, explains)
        self._explainer.fresh_session()
        self._warm_up()

    def _warm_up(self) -> None:
        """Open the models' connections now: the first sentence should not wait for them (D-42)."""
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

    def interrupted(self) -> None:
        """Someone talked over Mochi and it was cut short: it goes back to just listening.

        Example: in a meeting, the sentence after `interrupted()` is not taken as said to Mochi.
        """
        self._talk.hush()

    def reset(self) -> None:
        """Clear saved words and Mochi's conversation (demo reset)."""
        self._memory.reset()
        self._talk.reset()
