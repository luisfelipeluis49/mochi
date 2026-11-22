"""Composition root: builds every dependency from `Settings`. Nothing else constructs adapters."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial

from mochi_backend.gateway.activity_service import ActivityService
from mochi_backend.gateway.agora.client_port import AgoraAgentClient, RtcTokenIssuer, SpeechTuning
from mochi_backend.gateway.agora.local_mock import LocalMockAgoraClient, LocalMockTokenIssuer
from mochi_backend.gateway.agora.rest_client import AgoraRestClient
from mochi_backend.gateway.agora.token_issuer import AgoraTokenIssuer
from mochi_backend.gateway.connections import ConnectionService
from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.demo_reset import DemoReset
from mochi_backend.gateway.device_link import DeviceLink
from mochi_backend.gateway.device_service import DeviceService
from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.intelligence_port import IntelligencePort, StreamingDecider
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.roster import DEMO_USERS, GUEST_USER, SESSION_ID
from mochi_backend.gateway.session_history import SessionHistory
from mochi_backend.gateway.session_registry import SessionRegistry, SessionRuntime
from mochi_backend.gateway.session_service import SessionConfig, SessionService
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.gateway.turn_pipeline import PipelineDeps, TurnPipeline
from mochi_backend.gateway.user_directory import (
    RandomSuffix,
    SuffixSource,
    UserDirectory,
    voice_owners,
)
from mochi_backend.gateway.voice_directory import VoiceDirectory
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.memory_store import MemoryStore
from mochi_backend.intelligence.model_port import HintModel, NullHintModel
from mochi_backend.intelligence.openai_character_model import (
    CharacterModelConfig,
    OpenAiCharacterModel,
)
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.intelligence.service import Intelligence
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.clock import Clock, SystemClock
from mochi_backend.platform.http_client import HttpxClient, JsonValue
from mochi_backend.platform.ids import IdGenerator, UuidIdGenerator
from mochi_backend.platform.json_logging import EventLogger, configure_json_logging
from mochi_backend.platform.scheduler import AsyncioScheduler, Scheduler
from mochi_backend.settings import Settings
from mochi_backend.storage.event_log import StorageEventSink
from mochi_backend.storage.factory import StorageStart, storage_for
from mochi_contracts import Language

LLM_PATH = "/agora/llm/demo/chat/completions"  # SessionConfig.for_session swaps `demo`
MAX_KEYWORDS = 128  # what ARES accepts (Agora join page)


@dataclass(frozen=True)
class Adapters:
    """The replaceable outer pieces. Tests pass fakes; production uses `default_adapters`."""

    clock: Clock
    ids: IdGenerator
    scheduler: Scheduler
    logger: EventLogger
    agora: AgoraAgentClient
    tokens: RtcTokenIssuer
    intelligence: IntelligencePort
    intelligence_name: str
    storage: StorageStart = field(default_factory=StorageStart)
    # A new conversation over the same saved words, one per session. None: every session shares
    # `intelligence` (a fake in a test).
    brain_factory: Callable[[], IntelligencePort] | None = None
    # The 6 random hex characters of a new web user's id (D-42).
    suffixes: SuffixSource = field(default_factory=RandomSuffix)


@dataclass(frozen=True)
class SharedParts:
    """What every session uses in common besides the hub: voices and finished-session records."""

    voices: VoiceDirectory
    history: SessionHistory


def _model_for(settings: Settings, logger: EventLogger) -> HintModel:
    if not settings.model_configured:
        return NullHintModel()
    return _openai_hints(settings, logger)


def _openai_hints(settings: Settings, logger: EventLogger) -> HintModel:
    return (
        OpenAiHintModel(
            HttpxClient(),
            settings.mochi_model_base_url,
            settings.mochi_model_name,
            settings.model_api_key,
            settings.mochi_decide_timeout_seconds,
        )
        .thinking(settings.mochi_model_reasoning_effort)
        .logging(logger)
    )


def _agora_for(
    settings: Settings, clock: Clock, ids: IdGenerator, logger: EventLogger
) -> tuple[AgoraAgentClient, RtcTokenIssuer]:
    """Agora's REST client and token issuer, or the local mock in fake mode."""
    if settings.mochi_agora_mode == "fake":
        return LocalMockAgoraClient(logger), LocalMockTokenIssuer()
    creds = (settings.agora_rest_key, settings.agora_rest_secret)
    secrets = (settings.model_api_key, settings.mochi_turn_key, settings.mochi_device_key)
    rest = AgoraRestClient(HttpxClient(), settings.agora_app_id, *creds, ids)
    tokens = AgoraTokenIssuer(settings.agora_app_id, settings.agora_app_certificate, clock)
    return rest.hide_secrets((*secrets, *creds)), tokens


def default_adapters(settings: Settings) -> Adapters:
    """Real adapters; `MOCHI_AGORA_MODE=fake` swaps Agora for a local mock."""
    clock, ids = SystemClock(), UuidIdGenerator()
    logger = configure_json_logging(settings.mochi_log_level)
    agora, tokens = _agora_for(settings, clock, ids, logger)
    seeded = [*DEMO_USERS, GUEST_USER]  # guest's words need its row (foreign key; D-42)
    storage = storage_for(settings.database_url, logger, seeded, settings.mochi_local_data)
    brain = _brain_for(settings, (clock, ids, logger), storage)
    name = "rules+model" if settings.model_configured else "rules"
    name += "+character" if settings.character_configured else ""
    scheduler = AsyncioScheduler(logger)
    shared = (agora, tokens, brain, name, storage)
    return Adapters(
        clock, ids, scheduler, logger, *shared, brain_factory=brain.another_conversation
    )


def _brain_for(
    settings: Settings, plumbing: tuple[Clock, IdGenerator, EventLogger], start: StorageStart
) -> Intelligence:
    """Mochi's brain, with the words saved before a restart and a sink that keeps new ones."""
    clock, ids, logger = plumbing
    tuning = IntelligenceSettings(
        hint_ttl_seconds=settings.mochi_hint_ttl_seconds,
        model_timeout_seconds=settings.mochi_decide_timeout_seconds,
        character_timeout_seconds=settings.mochi_character_timeout_seconds,
        follow_up_seconds=settings.mochi_follow_up_seconds,
        hint_cooldown=settings.mochi_hint_cooldown,
    )
    brain = Intelligence(
        clock=clock,
        ids=ids,
        model=_model_for(settings, logger),
        settings=tuning,
    )
    brain.keep_words_in(MemoryStore(start.events, StorageEventSink(start.storage)))
    if settings.character_configured:
        brain.speak_as(_openai_character(settings, logger))
    return brain


def _openai_character(settings: Settings, logger: EventLogger) -> OpenAiCharacterModel:
    http = HttpxClient()
    model = OpenAiCharacterModel(http, _character_model(settings), logger)
    return model.streaming(http) if settings.streams_reply else model


def _streamer(settings: Settings, intelligence: IntelligencePort) -> StreamingDecider | None:
    """The intelligence that may stream Mochi's line, only with MOCHI_STREAM_REPLY (D-37)."""
    if settings.streams_reply and isinstance(intelligence, StreamingDecider):
        return intelligence
    return None


def _character_model(settings: Settings) -> CharacterModelConfig:
    return CharacterModelConfig(
        base_url=settings.mochi_model_base_url,
        model_name=settings.mochi_character_model_name,
        api_key=settings.model_api_key,
        timeout_seconds=settings.mochi_character_timeout_seconds,
        reasoning_effort=settings.mochi_character_reasoning_effort,
        hedge_after_seconds=settings.mochi_character_hedge_seconds,
    )


def vocabulary(settings: Settings) -> tuple[str, ...]:
    """The names and words speech-to-text should expect: `MOCHI_ASR_KEYWORDS` plus the lexicon.

    Example: `vocabulary(settings)[:2]` is `("Mochi", "adiar")`.
    """
    words = list(settings.mochi_asr_keywords)
    if settings.mochi_asr_lexicon_words:
        for entry in Lexicon.load().entries:
            words += [entry.word(Language.PT_BR), entry.word(Language.EN)]
    return tuple(dict.fromkeys(words))[:MAX_KEYWORDS]


def _ares_ears(settings: Settings, words: tuple[str, ...]) -> SpeechTuning:
    """Agora's own recogniser, hearing both languages, with the words as keywords."""
    return SpeechTuning(
        asr_vendor="ares",
        asr_language=settings.mochi_ares_language,
        asr_keywords=words,
        tts_vendor=settings.mochi_tts_vendor,
        tts_params=settings.mochi_tts_params,
        tts_credential_mode=settings.mochi_tts_credential_mode,
        end_of_speech_silence_ms=settings.mochi_end_of_speech_silence_ms,
        interruption=settings.mochi_interruption,
    )


def _openai_ears(settings: Settings, words: tuple[str, ...]) -> dict[str, JsonValue]:
    """`asr.params` for OpenAI transcription: the model, and a prompt that names the words."""
    hint = f"{settings.mochi_asr_prompt} Words that may come up: {', '.join(words)}."
    listening: dict[str, JsonValue] = {
        "model": settings.mochi_asr_openai_model,
        "prompt": hint,
        "language": settings.mochi_asr_language[:2].lower(),
    }
    given = settings.mochi_asr_params
    return {"api_key": settings.model_api_key, "input_audio_transcription": listening, **given}


def speech_tunings(settings: Settings) -> tuple[SpeechTuning, SpeechTuning | None]:
    """The ears a session starts with, and the ones to use if Agora refuses those.

    OpenAI transcription needs the model key; without one ARES is the only choice.
    Example: `speech_tunings(settings)[1]` is the ARES tuning, or None when ARES is already first.
    """
    words = vocabulary(settings)
    ares = _ares_ears(settings, words)
    vendor = settings.mochi_asr_vendor
    if vendor == "ares" or (vendor == "openai" and not settings.model_api_key):
        return ares, None
    params = _openai_ears(settings, words) if vendor == "openai" else settings.mochi_asr_params
    first = replace(
        ares,
        asr_vendor=vendor,
        asr_language=settings.mochi_asr_language,
        asr_keywords=(),  # Agora accepts keywords for ARES only
        asr_params=params,
        asr_credential_mode=settings.mochi_asr_credential_mode,
    )
    return first, ares


def _session_config(settings: Settings) -> SessionConfig:
    first, fallback = speech_tunings(settings)
    return SessionConfig(
        app_id=settings.agora_app_id,
        channel=settings.mochi_channel,
        pi_uid=settings.mochi_pi_uid,
        agent_uid=settings.mochi_agent_uid,
        token_ttl_seconds=settings.mochi_token_ttl_seconds,
        llm_url=settings.mochi_public_url.rstrip("/") + LLM_PATH,
        llm_key=settings.mochi_turn_key,
        idle_timeout_seconds=settings.mochi_agent_idle_timeout_seconds,
        tuning=first,
        fallback_tuning=fallback,
        greeting_en=settings.mochi_greeting_en,
        greeting_pt=settings.mochi_greeting_pt,
    )


def _core(
    settings: Settings, adapters: Adapters, hub: EventHub, brain: IntelligencePort
) -> GatewayCore:
    silence = SilencePolicy(
        settings.mochi_silence_strategy,
        adapters.clock,
        settings.mochi_speak_base_seconds,
        settings.mochi_speak_seconds_per_word,
    )
    live = LiveHint(hub, adapters.clock, adapters.scheduler)
    return GatewayCore(
        store=SessionStore(),
        hub=hub,
        live_hint=live,
        intelligence=brain,
        silence=silence,
        clock=adapters.clock,
        ids=adapters.ids,
        logger=adapters.logger,
        commit=asyncio.Lock(),
    )


def _pipeline(settings: Settings, core: GatewayCore, voices: VoiceDirectory) -> TurnPipeline:
    return TurnPipeline(
        PipelineDeps(
            store=core.store,
            hub=core.hub,
            live_hint=core.live_hint,
            intelligence=core.intelligence,
            silence=core.silence,
            clock=core.clock,
            ids=core.ids,
            logger=core.logger,
            decide_timeout_seconds=settings.turn_timeout_seconds,
            commit_lock=core.commit,
            ears_prompt=settings.mochi_asr_prompt + " Words that may come up:",
            ears_words=vocabulary(settings),
            voices=voices,
            cancel_stale_turns=settings.mochi_cancel_stale_turns,
            streamer=_streamer(settings, core.intelligence),
        )
    )


def _devices(core: GatewayCore, adapters: Adapters, config: SessionConfig) -> DeviceService:
    return DeviceService(
        store=core.store,
        tokens=adapters.tokens,
        silence=core.silence,
        config=config,
        clock=core.clock,
    )


def _game(core: GatewayCore, pipeline: TurnPipeline, agora: AgoraAgentClient) -> ActivityService:
    """Describe & Guess; the pipeline can start a round when Mochi writes `[play]` in a turn."""
    activity = ActivityService(core, pipeline, agora)
    pipeline.play_with(activity.start_in_turn)
    return activity


def _runtime(
    session_id: str, settings: Settings, adapters: Adapters, hub: EventHub, shared: SharedParts
) -> SessionRuntime:
    """One session's parts. The demo session uses the main brain; another gets its own."""
    config = _session_config(settings).for_session(session_id)
    core = _core(settings, adapters, hub, _brain_of(session_id, adapters))
    pipeline = _pipeline(settings, core, shared.voices)
    return SessionRuntime(
        session_id=session_id,
        core=core,
        pipeline=pipeline,
        sessions=SessionService(core, adapters.agora, adapters.tokens, config, shared.history),
        activity=_game(core, pipeline, adapters.agora),
        demo_reset=DemoReset(core),
    )


def _brain_of(session_id: str, adapters: Adapters) -> IntelligencePort:
    """The demo session's brain is the main one; another session talks with its own."""
    if session_id == SESSION_ID or adapters.brain_factory is None:
        return adapters.intelligence
    return adapters.brain_factory()


def build_container(settings: Settings, adapters: Adapters) -> AppContainer:
    """Wire the gateway from settings and adapters.

    The demo session (the Pi's) is built now; any other is built by its first Start.
    Example: `build_container(settings, default_adapters(settings))`.
    """
    hub = EventHub(adapters.clock, adapters.ids, adapters.logger)
    start = adapters.storage
    # Voices belong to the Pi's people only: a web user called "Ana" must not take Ana's voice.
    voices = VoiceDirectory(start.storage, start.voices, voice_owners(start.users))
    shared = SharedParts(voices, SessionHistory(start.storage, start.sessions))
    demo = _runtime(SESSION_ID, settings, adapters, hub, shared)
    others = partial(_other_runtime, settings, adapters, hub, shared)
    registry = SessionRegistry(demo, others)
    return _assemble(settings, adapters, (demo, registry, shared), hub)


def _assemble(
    settings: Settings,
    adapters: Adapters,
    parts: tuple[SessionRuntime, SessionRegistry, SharedParts],
    hub: EventHub,
) -> AppContainer:
    demo, registry, shared = parts
    core, start = demo.core, adapters.storage
    return AppContainer(
        settings=settings,
        core=core,
        pipeline=demo.pipeline,
        sessions=demo.sessions,
        activity=demo.activity,
        devices=_devices(core, adapters, _session_config(settings)),
        device_link=DeviceLink(core, adapters.agora),
        connections=ConnectionService(hub, adapters.intelligence, registry),
        demo_reset=demo.demo_reset,
        voices=shared.voices,
        intelligence_name=adapters.intelligence_name,
        registry=registry,
        users=UserDirectory(start.storage, start.users, adapters.suffixes),
        history=shared.history,
        storage_name=adapters.storage.name,
        storage_unsaved=adapters.storage.storage.unsaved_writes,
    )


def _other_runtime(
    settings: Settings,
    adapters: Adapters,
    hub: EventHub,
    shared: SharedParts,
    session_id: str,
) -> SessionRuntime:
    """A session opened by a client: its own hub view, store, brain and Agora channel."""
    return _runtime(session_id, settings, adapters, hub.for_session(session_id), shared)
