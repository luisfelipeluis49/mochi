"""Every environment variable, typed. Invalid values fail at startup with a readable message."""

from typing import Literal, Self

from pydantic import ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mochi_backend.platform.http_client import JsonValue

VendorParams = dict[str, JsonValue]
_SECRET_MARKERS = ("key", "secret", "certificate", "token")
_REAL_MODE_REQUIRED = (
    "agora_app_id",
    "agora_app_certificate",
    "agora_rest_key",
    "agora_rest_secret",
    "mochi_turn_key",
)


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
    model_api_key: str = ""
    mochi_public_url: str = "http://localhost:8000"
    mochi_agora_mode: Literal["fake", "real"] = "real"
    mochi_silence_strategy: Literal["empty_reply", "mute_speaker"] = "empty_reply"
    mochi_hint_ttl_seconds: float = 8.0
    mochi_decide_timeout_seconds: float = 2.0
    mochi_enable_dev_routes: bool = False
    mochi_channel: str = "mochi-demo"
    mochi_pi_uid: int = 1001
    mochi_agent_uid: int = 1002
    mochi_token_ttl_seconds: int = 3600
    mochi_cors_origins: str = "*"
    mochi_log_level: str = "INFO"
    mochi_model_base_url: str = "https://api.openai.com/v1"
    mochi_model_name: str = "gpt-4o-mini"
    # Mochi's own voice: with a model key it answers in character when spoken to (DECISIONS D-23)
    mochi_character_enabled: bool = True
    mochi_character_model_name: str = "gpt-4.1-mini"
    mochi_character_timeout_seconds: float = 6.0
    mochi_follow_up_seconds: float = 20.0
    mochi_greeting_en: str = "Hi! I'm listening."
    mochi_greeting_pt: str = "Oi! Pode falar."
    mochi_asr_vendor: str = "ares"
    mochi_asr_language: str = (
        "en-US,pt-PT"  # ARES has no Brazilian variant: pt-PT is its Portuguese
    )
    mochi_asr_keywords: list[str] = ["Mochi"]
    mochi_asr_params: VendorParams = {}
    mochi_asr_credential_mode: str = ""
    mochi_tts_vendor: str = "minimax"
    mochi_tts_params: VendorParams = {}
    mochi_tts_credential_mode: str = ""
    mochi_end_of_speech_silence_ms: int = 900
    mochi_agent_idle_timeout_seconds: int = 60
    mochi_speak_base_seconds: float = 0.6
    mochi_speak_seconds_per_word: float = 0.45
    port: int = 8000

    @model_validator(mode="after")
    def _real_mode_needs_credentials(self) -> Self:
        if self.mochi_agora_mode == "fake":
            self.mochi_turn_key = self.mochi_turn_key or "dev-turn-key"
            return self
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
