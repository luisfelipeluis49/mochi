"""Composition root: builds every dependency from `Settings`. Nothing else constructs adapters."""

import asyncio
from dataclasses import dataclass, replace

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
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.session_service import SessionConfig, SessionService
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.gateway.turn_pipeline import PipelineDeps, TurnPipeline
from mochi_backend.intelligence.lexicon import Lexicon
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
from mochi_contracts import Language

LLM_PATH = "/agora/llm/demo/chat/completions"
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


def _model_for(settings: Settings) -> HintModel:
    if not settings.model_configured:
        return NullHintModel()
    return OpenAiHintModel(
        HttpxClient(),
        settings.mochi_model_base_url,
        settings.mochi_model_name,
        settings.model_api_key,
        settings.mochi_decide_timeout_seconds,
    ).thinking(settings.mochi_model_reasoning_effort)


def default_adapters(settings: Settings) -> Adapters:
    """Real adapters; `MOCHI_AGORA_MODE=fake` swaps Agora for a local mock."""
    clock, ids = SystemClock(), UuidIdGenerator()
    logger = configure_json_logging(settings.mochi_log_level)
    if settings.mochi_agora_mode == "fake":
        agora: AgoraAgentClient = LocalMockAgoraClient(logger)
        tokens: RtcTokenIssuer = LocalMockTokenIssuer()
    else:
        creds = (settings.agora_rest_key, settings.agora_rest_secret)
        agora = AgoraRestClient(HttpxClient(), settings.agora_app_id, *creds, ids)
        tokens = AgoraTokenIssuer(settings.agora_app_id, settings.agora_app_certificate, clock)
    brain = _brain_for(settings, clock, ids, logger)
    name = "rules+model" if settings.model_configured else "rules"
    name += "+character" if settings.character_configured else ""
    return Adapters(clock, ids, AsyncioScheduler(logger), logger, agora, tokens, brain, name)


def _brain_for(
    settings: Settings, clock: Clock, ids: IdGenerator, logger: EventLogger
) -> Intelligence:
    tuning = IntelligenceSettings(
        hint_ttl_seconds=settings.mochi_hint_ttl_seconds,
        model_timeout_seconds=settings.mochi_decide_timeout_seconds,
        character_timeout_seconds=settings.mochi_character_timeout_seconds,
        follow_up_seconds=settings.mochi_follow_up_seconds,
        hint_cooldown=settings.mochi_hint_cooldown,
    )
    brain = Intelligence(clock=clock, ids=ids, model=_model_for(settings), settings=tuning)
    if settings.character_configured:
        brain.speak_as(OpenAiCharacterModel(HttpxClient(), _character_model(settings), logger))
    return brain


def _character_model(settings: Settings) -> CharacterModelConfig:
    return CharacterModelConfig(
        base_url=settings.mochi_model_base_url,
        model_name=settings.mochi_character_model_name,
        api_key=settings.model_api_key,
        timeout_seconds=settings.mochi_character_timeout_seconds,
        reasoning_effort=settings.mochi_character_reasoning_effort,
    )


def vocabulary(settings: Settings) -> tuple[str, ...]:
    """The names and words speech-to-text should expect: `MOCHI_ASR_KEYWORDS` plus the lexicon.

    Example: `vocabulary(settings)[:2]` is `("Mochi", "adiar")`.
    """
    words = list(settings.mochi_asr_keywords)
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


def _core(settings: Settings, adapters: Adapters) -> GatewayCore:
    hub = EventHub(adapters.clock, adapters.ids, adapters.logger)
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
        intelligence=adapters.intelligence,
        silence=silence,
        clock=adapters.clock,
        ids=adapters.ids,
        logger=adapters.logger,
        commit=asyncio.Lock(),
    )


def _pipeline(settings: Settings, core: GatewayCore) -> TurnPipeline:
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


def build_container(settings: Settings, adapters: Adapters) -> AppContainer:
    """Wire the gateway from settings and adapters.

    Example: `build_container(settings, default_adapters(settings))`.
    """
    core = _core(settings, adapters)
    config = _session_config(settings)
    pipeline = _pipeline(settings, core)
    return AppContainer(
        settings=settings,
        core=core,
        pipeline=pipeline,
        sessions=SessionService(core, adapters.agora, adapters.tokens, config),
        activity=ActivityService(core, pipeline, adapters.agora),
        devices=_devices(core, adapters, config),
        device_link=DeviceLink(core, adapters.agora),
        connections=ConnectionService(core.hub, core.store, core.live_hint),
        demo_reset=DemoReset(core),
        intelligence_name=adapters.intelligence_name,
    )
