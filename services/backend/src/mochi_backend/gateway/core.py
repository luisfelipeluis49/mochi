"""The collaborators almost every gateway service needs, bundled so constructors stay small."""

import asyncio
from dataclasses import dataclass

from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.platform.clock import Clock
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.json_logging import EventLogger
from mochi_backend.team.journal import SessionJournal


@dataclass(frozen=True)
class GatewayCore:
    """Built once by the composition root."""

    store: SessionStore
    hub: EventHub
    live_hint: LiveHint
    intelligence: IntelligencePort
    silence: SilencePolicy
    clock: Clock
    ids: IdGenerator
    logger: EventLogger
    journal: SessionJournal  # what this session adds to the company's learning history
    # Held while a turn, Stop or Reset publishes its results, so none of them
    # interleaves with another. Not re-entrant: take it only at those entry points.
    commit: asyncio.Lock
