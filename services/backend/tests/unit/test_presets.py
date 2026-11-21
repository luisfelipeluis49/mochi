"""config/presets/*.env load into valid Settings and give the ears and voice they promise.

Each preset is sourced by bash exactly as scripts/_lib.sh `load_preset` does (prod.env first), with
no ./.env, then fed to Settings through the environment (so JSON lists parse as in production).
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from mochi_backend.composition import speech_tunings, vocabulary
from mochi_backend.settings import Settings

ROOT = Path(__file__).resolve().parents[4]
PRESETS = ROOT / "config" / "presets"
SCRIPTS = ROOT / "scripts"
NAMES = ("prod", "safe", "ares", "cartesia", "stream", "likely", "stretch")
SHELL_SCRIPTS = (
    "_lib.sh",
    "with-preset.sh",
    "start-test-backend.sh",
    "latency-compare.sh",
    "cost-estimate.sh",
    "keep-warm.sh",
)
FAKE_SECRETS = {"MOCHI_AGORA_MODE": "fake", "MODEL_API_KEY": "sk-test-not-real"}


def _preset_env(name: str) -> dict[str, str]:
    """The variables a preset sets, read back from bash after `set -a; . prod.env; . NAME.env`."""
    layered = f'. "{PRESETS}/prod.env"' + ("" if name == "prod" else f'; . "{PRESETS}/{name}.env"')
    command = f"set -a; {layered}; set +a; env -0"
    clean = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    argv = ["bash", "-c", command]
    out = subprocess.run(argv, check=True, capture_output=True, env=clean).stdout.decode()  # noqa: S603
    pairs = (item.partition("=") for item in out.split("\0") if item)
    return {k: v for k, _, v in pairs if k.startswith("MOCHI_")}


def _settings(name: str, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key in [k for k in os.environ if k.startswith("MOCHI_") or k == "DATABASE_URL"]:
        monkeypatch.delenv(key)
    for key, value in {**_preset_env(name), **FAKE_SECRETS}.items():
        monkeypatch.setenv(key, value)
    return Settings()


@pytest.mark.parametrize("name", NAMES)
def test_every_preset_loads_into_settings(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(name, monkeypatch)
    assert settings.mochi_hint_cooldown == "while_shown"
    assert settings.mochi_model_name == "gpt-5.4-mini"


def test_prod_is_openai_ears_and_minimax_with_every_new_flag_off() -> None:
    env = _preset_env("prod")
    assert env["MOCHI_ASR_VENDOR"] == "openai" and env["MOCHI_ASR_LEXICON_WORDS"] == "false"
    assert json.loads(env["MOCHI_TTS_PARAMS"])["model"] == "speech-2.8-turbo"
    assert env["MOCHI_END_OF_SPEECH_SILENCE_MS"] == "600"
    flags = ("MOCHI_CANCEL_STALE_TURNS", "MOCHI_CHARACTER_HEDGE_SECONDS", "MOCHI_STREAM_REPLY")
    assert [env[f] for f in flags] == ["false", "0", "false"]


@pytest.mark.parametrize("name", ["ares", "likely", "stretch"])
def test_ares_arms_send_the_24_probed_keywords(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(name, monkeypatch)
    first, fallback = speech_tunings(settings)
    assert (first.asr_vendor, first.asr_language, fallback) == ("ares", "en-US,pt-BR", None)
    assert len(first.asr_keywords) == 24 and first.asr_keywords == vocabulary(settings)
    assert {"adiar", "guarda-chuva", "Oi Mochi"} <= set(first.asr_keywords)


@pytest.mark.parametrize("name", ["cartesia", "likely", "stretch"])
def test_cartesia_arms_use_managed_sonic(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    first, _ = speech_tunings(_settings(name, monkeypatch))
    assert (first.tts_vendor, first.tts_credential_mode) == ("cartesia", "managed")
    assert first.tts_params["model_id"] == "sonic-3.6"
    assert first.tts_params["voice"] == {"mode": "id", "id": "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"}


def _changes(name: str) -> dict[str, str]:
    prod = _preset_env("prod")
    return {k: v for k, v in _preset_env(name).items() if prod.get(k) != v}


def test_combined_presets_are_the_sum_of_their_parts() -> None:
    parts = {**_preset_env("prod"), **_changes("safe"), **_changes("ares"), **_changes("cartesia")}
    assert _preset_env("likely") == parts
    stretch = {**parts, **_changes("stream"), "MOCHI_END_OF_SPEECH_SILENCE_MS": "480"}
    assert _preset_env("stretch") == stretch


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_shell_scripts_parse(script: str) -> None:
    subprocess.run(["bash", "-n", str(SCRIPTS / script)], check=True)  # noqa: S603, S607


def test_test_backend_refuses_production_targets() -> None:
    for args in (["prod", "https://mochi.onrender.com"], ["prod", "http://localhost:8000"]):
        argv = ["bash", str(SCRIPTS / "start-test-backend.sh"), *args]
        done = subprocess.run(argv, capture_output=True, check=False)  # noqa: S603
        assert done.returncode == 2, done.stderr
