"""scripts/cost_estimate.py: prices, log parsing and the per-arm estimate. No network."""

import json
from pathlib import Path

import cost_estimate as ce
import pytest

from mochi_backend.platform.http_client import HttpResponse
from tests.fakes.fake_http_getter import FakeHttpGetter

PRICES = ce.load_prices(ce.PRICES_FILE)


def _line(event: str, **fields: object) -> str:
    return "INFO: " + json.dumps({"ts": "t", "level": "INFO", "event": event, **fields})


def _usage(kind: str, prompt: int, completion: int, cached: int = 0) -> str:
    return _line(
        "model_usage",
        model="gpt-5.4-mini",
        kind=kind,
        prompt_tokens=prompt,
        completion_tokens=completion,
        cached_tokens=cached,
        latency_ms=700,
    )


LOG = [
    "INFO:     Uvicorn running on http://127.0.0.1:8000",
    _line("agent_started", agent_id="OLD"),
    _usage("hint", 9_000_000, 0),
    _line("agent_started", agent_id="A1"),
    _usage("hint", 1_000_000, 0, cached=1_000_000),
    _usage("character", 1_000_000, 1_000_000),
    _line("character_hedge_used", segment_id="seg_1"),
    _line("model_usage", model="mystery-model", prompt_tokens=5),
    "not json {",
]


def test_every_price_names_its_source_and_whether_it_was_verified() -> None:
    assert PRICES.agora_audio_task.per_minute == 0.10
    assert PRICES.models["gpt-5.4-mini"].output_per_mtok == 4.50
    assert PRICES.tts_per_minute["cartesia"].verified is False
    assert all(p.source.startswith("https://") for p in PRICES.models.values())


def test_cached_tokens_are_part_of_the_prompt_and_cheaper() -> None:
    price = PRICES.models["gpt-5.4-mini"]
    half = ce.ModelUsage(model="m", prompt_tokens=2_000_000, cached_tokens=1_000_000)
    assert ce.call_cost(half, price) == pytest.approx(0.75 + 0.075)


def test_dated_model_names_find_their_price() -> None:
    assert ce.model_price(PRICES, "gpt-5.4-mini-2026-03-17") is PRICES.models["gpt-5.4-mini"]
    assert ce.model_price(PRICES, "mystery-model") is None


def test_only_the_agents_own_session_is_counted() -> None:
    records = ce.session_records(ce.log_records(LOG), "A1")
    assert [u.model for u in ce.usages(records)] == [
        "gpt-5.4-mini",
        "gpt-5.4-mini",
        "mystery-model",
    ]
    assert len(ce.usages(ce.session_records(ce.log_records(LOG), ""))) == 4
    assert ce.session_records(ce.log_records(LOG), "NOPE") == []


def test_openai_ears_cost_per_minute_and_ares_does_not() -> None:
    records = ce.session_records(ce.log_records(LOG), "A1")
    prod = ce.arm_cost(ce.parse_arm("PROD,openai,minimax,10"), 10.0, records, PRICES)
    ares = ce.arm_cost(ce.parse_arm("ARES,ares,cartesia,10"), 10.0, records, PRICES)
    assert prod.agora == pytest.approx(1.0)
    assert prod.transcription == pytest.approx(0.06)
    assert ares.transcription == 0.0
    assert prod.models == pytest.approx(0.075 + 0.75 + 4.50)
    assert prod.model_calls == 3 and prod.unpriced_models == ("mystery-model",)
    assert prod.hedges == 1 and prod.hedge_estimate == pytest.approx(5.25)
    assert ares.unverified == ("cartesia TTS",) and prod.unverified == ()


def test_report_scales_to_ten_minutes_and_flags_unverified_billing() -> None:
    arm = ce.arm_cost(ce.parse_arm("C,ares,cartesia,5"), 5.0, [], PRICES)
    text = ce.report([arm])
    assert "| C | 5.0 | $0.5000 |" in text
    assert "| $0.5000 | $1.0000 |" in text
    assert "UNVERIFIED: cartesia TTS billing" in text


def test_arm_spec_shape_is_checked() -> None:
    assert ce.parse_arm("P,openai,minimax,A1,x.log").log == "x.log"
    with pytest.raises(ValueError, match="LABEL,ASR,TTS,DURATION"):
        ce.parse_arm("P,openai")


async def test_minutes_come_from_the_agents_turns(tmp_path: Path) -> None:
    turns = {"turns": [{"start": {"start_at": 0}, "end": {"end_at": 90_000}}]}
    getter = FakeHttpGetter({"/agents/A1/turns": HttpResponse(200, json.dumps(turns))})
    assert await ce.resolve_minutes(getter, "A1") == (1.5, "A1")
    assert await ce.resolve_minutes(getter, "6.5") == (6.5, "")
    with pytest.raises(ValueError, match="pass the minutes"):
        await ce.resolve_minutes(getter, "UNKNOWN")


async def test_estimate_reads_the_log_file(tmp_path: Path) -> None:
    log = tmp_path / "run.log"
    log.write_text("\n".join(LOG), encoding="utf-8")
    costs = await ce.estimate(FakeHttpGetter({}), [f"P,openai,minimax,2,{log}"], PRICES)
    assert costs[0].model_calls == 4  # minutes given, no agent id: the whole log counts
