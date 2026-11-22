"""Builds the whole backend from fakes, so tests drive it end to end without I/O."""

from dataclasses import dataclass

from mochi_backend.composition import Adapters, build_container
from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.turn_pipeline import TurnOutcome
from mochi_backend.intelligence.character_port import CharacterModel
from mochi_backend.intelligence.coach_port import CoachModel
from mochi_backend.intelligence.explain_port import ExplainModel
from mochi_backend.intelligence.interpret_port import InterpretModel
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.intelligence.phrase_port import PhraseModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.settings import load_settings
from mochi_backend.storage.event_log import StorageEventSink
from mochi_backend.storage.factory import StorageStart
from mochi_backend.storage.port import NullStorage, Storage
from tests.fakes.fake_agora import FakeAgoraClient, FakeTokenIssuer
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_scheduler import FakeScheduler
from tests.fakes.fake_sender import FakeEventLogger, FakeSender
from tests.fakes.gated_intelligence import GatedIntelligence

ANA = ConnectionTarget("mobile", user_id="ana")
BEN = ConnectionTarget("mobile", user_id="ben")
ANA_AR = ConnectionTarget("glasses", user_id="ana")
BEN_AR = ConnectionTarget("glasses", user_id="ben")
HOME = ConnectionTarget("home", device_id="home_pi_01")
AUDIENCE = ConnectionTarget("audience")


@dataclass
class Harness:
    """The container plus every fake a test may want to inspect or script."""

    container: AppContainer
    clock: FakeClock
    scheduler: FakeScheduler
    agora: FakeAgoraClient
    tokens: FakeTokenIssuer
    logger: FakeEventLogger
    gate: GatedIntelligence | None = None

    async def connect(self, target: ConnectionTarget) -> FakeSender:
        """Open a fake client (it receives the snapshot first)."""
        sender = FakeSender()
        await self.container.connections.accept(target, sender)
        return sender

    async def connect_all(self, *targets: ConnectionTarget) -> list[FakeSender]:
        """Open one fake client per target, in order."""
        return [await self.connect(target) for target in targets]

    async def say(self, text: str, gap_seconds: float = 1.0) -> TurnOutcome:
        """Advance the clock, then run one turn (cooldown depends on time moving)."""
        self.clock.advance(gap_seconds)
        return await self.container.pipeline.handle_turn(text)


def _brain(
    clock: FakeClock,
    ids: SequentialIdGenerator,
    model: FakeHintModel | None,
    character: CharacterModel | None,
    tuning: IntelligenceSettings,
) -> Intelligence:
    brain = Intelligence(
        clock=clock,
        ids=ids,
        model=model or FakeHintModel(),
        settings=tuning,
    )
    if character is not None:
        brain.speak_as(character)
    return brain


def make_harness(  # noqa: PLR0913 - one switch per fake; see DECISIONS D-32
    *,
    env: dict[str, str] | None = None,
    intelligence: IntelligencePort | None = None,
    model: FakeHintModel | None = None,
    character: CharacterModel | None = None,
    gated: bool = False,
    storage: Storage | None = None,
    explains: ExplainModel | None = None,
    coach: CoachModel | None = None,
    phrases: PhraseModel | None = None,
    interprets: InterpretModel | None = None,
) -> Harness:
    """Fake-Agora backend. `env` overrides settings (e.g. MOCHI_SILENCE_STRATEGY).

    `character`: Mochi's scripted own lines (without one it keeps its fixed lines).
    `explains`, `coach` and `phrases`: the scripted models that explain an idiom, write a
    report, suggest the sentence someone was reaching for and speak for someone.
    """
    # The live transcript is off here unless a test asks for it: with it every sentence adds an
    # event and a device caption, and most tests count exactly what one feature publishes.
    # Likewise an asked word is not said aloud here unless a test asks (D-70): the older tests
    # were written when "como se diz X?" between two people got a silent hint.
    quiet = {
        "MOCHI_AGORA_MODE": "fake",
        "MOCHI_TURN_KEY": "k",
        "MOCHI_LIVE_TRANSCRIPT": "false",
        "MOCHI_SAY_ASKED_WORDS": "false",
    }
    settings = load_settings({**quiet, **(env or {})})
    clock, ids, logger = FakeClock(), SequentialIdGenerator(), FakeEventLogger()
    kept = storage or NullStorage()
    ttl = settings.mochi_hint_ttl_seconds
    start = StorageStart.read(kept, "memory")
    tuning = IntelligenceSettings(
        hint_ttl_seconds=ttl,
        model_timeout_seconds=2.0,
        explain_terms=settings.mochi_explain_terms,
        suggest_phrases=settings.mochi_suggest_phrases,
        speak_for_me=settings.mochi_speak_for_me,
        say_asked_words=settings.mochi_say_asked_words,
    )
    brain = intelligence or _brain(clock, ids, model, character, tuning)
    if isinstance(brain, Intelligence):
        brain.keep_words_in(MemoryStore(start.events, StorageEventSink(kept)))
        _ = explains and brain.explain_with(explains)  # type: ignore[func-returns-value]
        _ = coach and brain.coach_with(coach)  # type: ignore[func-returns-value]
        _ = phrases and brain.phrase_with(phrases)  # type: ignore[func-returns-value]
        _ = interprets and brain.interpret_with(interprets)  # type: ignore[func-returns-value]
    gate = GatedIntelligence(brain) if gated else None
    brain = gate or brain
    scheduler, agora, tokens = FakeScheduler(clock), FakeAgoraClient(), FakeTokenIssuer()
    own = brain.another_conversation if isinstance(brain, Intelligence) else None
    adapters = Adapters(
        clock, ids, scheduler, logger, agora, tokens, brain, "rules", start, brain_factory=own
    )
    container = build_container(settings, adapters)
    return Harness(container, clock, scheduler, agora, tokens, logger, gate)
