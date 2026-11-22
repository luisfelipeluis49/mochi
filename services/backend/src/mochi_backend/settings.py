"""Every environment variable, typed. Invalid values fail at startup with a readable message."""

from typing import Literal, Self

from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mochi_backend.platform.http_client import JsonValue

VendorParams = dict[str, JsonValue]
_SECRET_MARKERS = ("key", "secret", "certificate", "token", "database_url")
_REAL_MODE_REQUIRED = (
    "agora_app_id",
    "agora_app_certificate",
    "agora_rest_key",
    "agora_rest_secret",
    "mochi_turn_key",
    "mochi_device_key",
)
DEV_DEVICE_KEY = "dev-device-key"  # fake mode only; the Pi sends it as `Authorization: Bearer`


class SettingsError(Exception):
    """Raised at startup; names each variable, its (masked) value and the expected shape."""


class Settings(BaseSettings):
    """Environment variables (AGENTS 11 names plus MOCHI_* additions). See `.env.example`."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    agora_app_id: str = ""
    agora_app_certificate: str = ""
    agora_rest_key: str = ""
    agora_rest_secret: str = ""
    mochi_turn_key: str = ""
    mochi_device_key: str = ""
    model_api_key: str = ""
    database_url: str = ""  # Postgres; empty = memory only (lost on restart). See D-32
    mochi_local_data: str = ""  # a JSON file for saved words and voices; fake mode only. See D-33
    mochi_public_url: str = "http://localhost:8000"
    mochi_agora_mode: Literal["fake", "real"] = "real"
    mochi_silence_strategy: Literal["empty_reply", "mute_speaker"] = "empty_reply"
    mochi_hint_ttl_seconds: float = 8.0
    mochi_decide_timeout_seconds: float = 2.0
    mochi_enable_dev_routes: bool = False
    mochi_channel: str = "mochi-demo"
    mochi_pi_uid: int = 1001
    mochi_agent_uid: int = 1002
    # Longer than the longest session (the Pi's max_session_s is one hour): a token that ran out
    # at the hour would end a meeting a moment early.
    mochi_token_ttl_seconds: int = 7200
    mochi_cors_origins: str = "*"
    mochi_log_level: str = "INFO"
    mochi_model_base_url: str = "https://api.openai.com/v1"
    mochi_model_name: str = "gpt-4o-mini"
    mochi_model_reasoning_effort: str = ""  # "none" for the gpt-5 family; empty for the rest
    mochi_hint_cooldown: Literal["two_turns", "while_shown"] = "two_turns"  # DECISIONS D-29
    # Mochi's own voice: with a model key it answers in character when spoken to (DECISIONS D-23)
    mochi_character_enabled: bool = True
    mochi_character_model_name: str = "gpt-5.4-mini"
    mochi_character_reasoning_effort: str = "none"  # empty for models without it (gpt-4.1-mini)
    mochi_character_timeout_seconds: float = 6.0
    mochi_follow_up_seconds: float = 20.0
    # Said when the device wakes Mochi: a meeting begins, and Mochi listens without a sound.
    mochi_greeting_en: str = "Hi! I'm listening. Call me if you need a word."
    mochi_greeting_pt: str = "Oi! Estou ouvindo. Me chama se precisar de uma palavra."
    # The team view leaves out an expression fewer people than this needed, so a small team's
    # list cannot point at one person (DECISIONS D-45). 1 shows everything.
    mochi_team_min_people: int = 1
    # Whose sentences count in a meeting on the device. "all": everyone's (the default).
    # "registered": only a sentence a registered voice clearly said is looked at and stored; the
    # rest is dropped unseen. For a noisy room, where the people at the next table are heard too
    # (D-36, D-49). It has no effect where no voices are reported (a phone's microphone).
    mochi_meeting_voices: Literal["all", "registered"] = "all"
    # Each finished sentence goes to the screens of its session as `transcript.line`, and to the
    # device as a caption (DECISIONS D-51). Off: nothing of what is said is shown, as before.
    mochi_live_transcript: bool = True
    # An idiom or a technical term the listeners may not know is explained on screen (D-53).
    # One more small model call for each real sentence of a meeting; needs MODEL_API_KEY.
    mochi_explain_terms: bool = True
    # After Stop each person gets a private report of what was wrong in what they said (D-54).
    # One model call per person and session; needs MODEL_API_KEY.
    mochi_speech_reports: bool = True
    # After a hint, the whole sentence the speaker was reaching for is suggested; one touch and
    # Mochi says it aloud (D-59). One small model call per hint; needs MODEL_API_KEY.
    mochi_suggest_phrases: bool = True
    mochi_suggestion_ttl_seconds: float = 20.0  # how long the touch works after the suggestion
    mochi_report_model_name: str = ""  # empty: MOCHI_MODEL_NAME
    mochi_report_reasoning_effort: str = ""  # empty: "low" where the hint judge has a setting
    mochi_report_timeout_seconds: float = 60.0
    # Ears (DECISIONS D-25). "openai" needs MODEL_API_KEY; without one, or when Agora refuses the
    # request, ARES with keywords is used instead.
    mochi_asr_vendor: str = "openai"
    mochi_asr_language: str = "en-US"  # the main language, for every vendor but ARES
    mochi_asr_openai_model: str = "gpt-4o-transcribe"
    mochi_asr_prompt: str = (
        "People in a work meeting. They speak English and Brazilian Portuguese and "
        "often mix both in one sentence. Write every word in the language it was spoken in; "
        "never translate."
    )
    # Both languages as ONE string. "en-US,pt-BR" was also accepted by Agora (live probe 2026-11-21,
    # VERIFIED.md); how well it recognises is unmeasured, so the default stays pt-PT for now.
    mochi_ares_language: str = "en-US,pt-PT"
    mochi_asr_keywords: list[str] = ["Mochi"]  # names to expect
    # Also tell the ears the lexicon's words ("adiar", "chave", ...). It makes them hear those
    # words in unclear audio too: background speech came back as "I forgot my guarda-chuva." and
    # Mochi taught "umbrella" to nobody (DECISIONS D-35, D-36).
    mochi_asr_lexicon_words: bool = True
    mochi_asr_params: VendorParams = {}
    mochi_asr_credential_mode: str = ""
    mochi_tts_vendor: str = "minimax"
    mochi_tts_params: VendorParams = {}
    mochi_tts_credential_mode: str = ""
    # Below 600 ms risks splitting "trails off... um" turns in two.
    mochi_end_of_speech_silence_ms: int = 600
    # A sentence said while Mochi is still thinking or speaking. "" (Agora's default): it
    # interrupts, and the answer under way is thrown away, so a voice in the room right after a
    # question left the question unanswered. "append": Mochi finishes, then that sentence gets
    # its turn. "ignore": it is discarded (not while two people talk: quick replies would be lost).
    mochi_interruption: Literal["", "append", "ignore"] = ""
    mochi_agent_idle_timeout_seconds: int = 60
    mochi_speak_base_seconds: float = 0.6
    mochi_speak_seconds_per_word: float = 0.45
    # Latency levers (DECISIONS D-37). Each default is the behaviour before the lever existed.
    # A newer Agora request (or Agora hanging up) cancels the older turn's decide() and model calls.
    mochi_cancel_stale_turns: bool = False
    # Re-send Mochi's reply request after this many seconds without an answer; first answer wins.
    # 0 is off. Raises the model bill: every call slower than this is paid twice.
    mochi_character_hedge_seconds: float = 0.0
    # Stream Mochi's free-chat line to Agora while the model writes it (only with the
    # empty_reply silence strategy).
    mochi_stream_reply: bool = False
    port: int = 8000

    @field_validator("database_url")
    @classmethod
    def _database_url_is_postgres(cls, value: str) -> str:
        if value and not value.startswith(("postgres://", "postgresql://")):
            raise ValueError("must start with postgres:// or postgresql:// (or be empty)")
        return value

    @model_validator(mode="after")
    def _real_mode_needs_credentials(self) -> Self:
        if self.mochi_agora_mode == "fake":
            self.mochi_turn_key = self.mochi_turn_key or "dev-turn-key"
            self.mochi_device_key = self.mochi_device_key or DEV_DEVICE_KEY
            return self
        if self.mochi_local_data:
            raise ValueError(
                "MOCHI_LOCAL_DATA is for MOCHI_AGORA_MODE=fake only; a deployed container's disk "
                "is wiped on every deploy. Use DATABASE_URL"
            )
        missing = [name.upper() for name in _REAL_MODE_REQUIRED if not getattr(self, name)]
        if missing:
            raise ValueError(
                f"MOCHI_AGORA_MODE=real needs {missing}; set them, or use MOCHI_AGORA_MODE=fake"
            )
        if not self.mochi_public_url.startswith("https://"):
            raise ValueError(
                f"MOCHI_PUBLIC_URL={self.mochi_public_url!r} must start with https:// in real "
                "mode, because Agora's cloud calls this address (use scripts/tunnel.sh locally)"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        """`MOCHI_CORS_ORIGINS` split on commas."""
        return [o.strip() for o in self.mochi_cors_origins.split(",") if o.strip()]

    @property
    def model_configured(self) -> bool:
        """True when a model key is present (otherwise only the rule-based cases run)."""
        return bool(self.model_api_key)

    @property
    def character_configured(self) -> bool:
        """True when Mochi writes its own lines (a model key, and not switched off)."""
        return self.model_configured and self.mochi_character_enabled

    @property
    def streams_reply(self) -> bool:
        """MOCHI_STREAM_REPLY in effect: with `mute_speaker` the speaker is unmuted only once the
        whole reply is decided, so streamed words would play muted; it stays off there."""
        return self.mochi_stream_reply and self.mochi_silence_strategy == "empty_reply"

    @property
    def turn_timeout_seconds(self) -> float:
        """How long one turn may take to decide: the hint rules, plus Mochi's own reply if any."""
        extra = self.mochi_character_timeout_seconds if self.character_configured else 0.0
        return self.mochi_decide_timeout_seconds + extra


def _masked(name: str, value: object) -> str:
    return "***" if any(m in name.lower() for m in _SECRET_MARKERS) else repr(value)


def describe_errors(error: ValidationError) -> str:
    """One line per problem: variable, masked value, expected shape.

    Errors about the whole settings object carry no single value, so none is printed (the input
    could contain secrets that were set correctly).
    """
    lines = []
    for item in error.errors():
        if not item["loc"]:
            lines.append(str(item["msg"]))
            continue
        name = ".".join(str(part) for part in item["loc"]).upper()
        lines.append(f"{name}={_masked(name, item.get('input'))}: {item['msg']}")
    return "invalid settings: " + "; ".join(lines)


def load_settings(environment: dict[str, str] | None = None) -> Settings:
    """Read settings from the environment (or the given mapping, for tests).

    Example: `load_settings({"MOCHI_AGORA_MODE": "fake"}).mochi_turn_key` is "dev-turn-key".
    """
    try:
        if environment is None:
            return Settings()
        return Settings.model_validate({k.lower(): v for k, v in environment.items()})
    except ValidationError as error:
        raise SettingsError(describe_errors(error)) from error
