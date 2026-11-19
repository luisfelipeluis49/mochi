"""Builds the whole backend from fakes, so tests drive it end to end without I/O."""

from dataclasses import dataclass

from mochi_backend.composition import Adapters, build_container
from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.turn_pipeline import TurnOutcome
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.settings import load_settings
from tests.fakes.fake_agora import FakeAgoraClient, FakeTokenIssuer
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_hint_model import FakeHintModel
from tests.fakes.fake_scheduler import FakeScheduler
from tests.fakes.fake_sender import FakeEventLogger, FakeSender

ANA = ConnectionTarget("mobile", user_id="ana")
BEN = ConnectionTarget("mobile", user_id="ben")
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


def make_harness(
    *,
    env: dict[str, str] | None = None,
    intelligence: IntelligencePort | None = None,
    model: FakeHintModel | None = None,
) -> Harness:
    """Fake-Agora backend. `env` overrides settings (e.g. MOCHI_SILENCE_STRATEGY)."""
    settings = load_settings({"MOCHI_AGORA_MODE": "fake", "MOCHI_TURN_KEY": "k", **(env or {})})
    clock, ids, logger = FakeClock(), SequentialIdGenerator(), FakeEventLogger()
    brain = intelligence or Intelligence(
        clock=clock,
        ids=ids,
        model=model or FakeHintModel(),
        settings=IntelligenceSettings(settings.mochi_hint_ttl_seconds, 2.0),
    )
    scheduler, agora, tokens = FakeScheduler(clock), FakeAgoraClient(), FakeTokenIssuer()
    adapters = Adapters(clock, ids, scheduler, logger, agora, tokens, brain, "rules")
    return Harness(build_container(settings, adapters), clock, scheduler, agora, tokens, logger)
