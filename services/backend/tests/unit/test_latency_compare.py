"""scripts/latency_compare.py: which Agora turns count, and the per-arm tables. No network."""

import json
from pathlib import Path

import latency_compare as lc
import pytest

from mochi_backend.platform.http_client import HttpResponse
from tests.fakes.fake_http_getter import FakeHttpGetter

CREDENTIALS = ("app", "key", "secret")
type Segments = dict[str, int]


def _turn(start: str, end: str, segments: Segments, at: int = 0) -> dict[str, object]:
    e2e = sum(segments.values())
    return {
        "turn_id": at,
        "start": {"type": start, "start_at": 1_000_000 + at * 1000},
        "end": {"type": end, "end_at": 1_000_500 + at * 1000},
        "metrics": {
            "e2e_latency_ms": e2e,
            "segmented_latency_ms": [{"name": n, "latency": v} for n, v in segments.items()],
        },
    }


def _spoken(asr: int, llm: int, at: int = 0) -> dict[str, object]:
    segments = {"algorithm_processing": 200, "asr_ttlw": asr, "llm_ttft": llm, "llm_ftfs": 5}
    return _turn("voice_input", "ok", {**segments, "tts_ttfb": 320}, at)


def _body(*turns: dict[str, object]) -> str:
    return json.dumps({"agent_id": "A1", "turns": list(turns)})


GOLDEN_LIKE = _body(
    _turn("greeting", "ok", {"tts_ttfb": 392}, 1),
    _turn("voice_input", "interrupted", {"algorithm_processing": 200, "asr_ttlw": 983}, 2),
    _spoken(1000, 1300, 3),
    _turn("voice_input", "ok", {"algorithm_processing": 200, "asr_ttlw": 900, "llm_ttft": 800}, 4),
    _turn("api_speak", "ok", {"tts_ttfb": 330}, 5),
    _turn("voice_input", "interrupted", {"asr_ttlw": 1100, "llm_ttft": 900, "tts_ttfb": 300}, 6),
)


def test_only_uninterrupted_voice_turns_that_reached_the_llm_are_kept() -> None:
    arm = lc.arm_turns("PROD", GOLDEN_LIKE)
    assert [t["asr_ttlw"] for t in arm.spoken] == [1000]
    assert [t["llm_ttft"] for t in arm.silent] == [800]  # a hint turn: empty reply, no TTS
    assert arm.skipped == 4


def test_session_minutes_spans_first_start_to_last_end() -> None:
    assert lc.session_minutes(GOLDEN_LIKE) == pytest.approx((6500 - 1000) / 60000)
    assert lc.session_minutes(_body()) is None


def test_report_has_p50_p95_deltas_and_a_small_sample_warning() -> None:
    base = lc.arm_turns("PROD", _body(*(_spoken(1000, 1300, i) for i in range(3))))
    faster = lc.arm_turns("ARES", _body(*(_spoken(600, 1300, i) for i in range(10))))
    text = lc.report([base, faster])
    assert "| PROD | 3 | 200 / 200 | 1000 / 1000 | 1300 / 1300 |" in text
    assert "| ARES | 10 | +0 / +0 | -400 / -400 | +0 / +0 |" in text
    assert "WARNING: PROD has only 3 spoken turns" in text
    assert "WARNING: ARES" not in text


def test_percentiles_use_nearest_rank() -> None:
    arm = lc.arm_turns("X", _body(*(_spoken(asr, 1000, i) for i, asr in enumerate(range(1, 21)))))
    assert "| X | 20 | 200 / 200 | 10 / 19 |" in lc.stats_table([arm], spoken=True)


def test_arm_spec_needs_a_label_and_a_source() -> None:
    assert lc.parse_arm_spec("PROD=A46AF") == ("PROD", "A46AF")
    with pytest.raises(ValueError, match="LABEL=AGENT_ID"):
        lc.parse_arm_spec("A46AF")


async def test_turns_are_fetched_through_the_agora_turns_client() -> None:
    getter = FakeHttpGetter({"/agents/A1/turns": HttpResponse(200, GOLDEN_LIKE)})
    arms = await lc.collect(getter, CREDENTIALS, ["PROD=A1", "LATE=A2"])
    assert [len(arm.spoken) for arm in arms] == [1, 0]  # A2 answers 404: still running
    assert getter.urls[0].endswith("/app/agents/A1/turns")
    assert getter.headers[0]["Authorization"].startswith("Basic ")


async def test_a_saved_reply_file_is_read_instead_of_fetched(tmp_path: Path) -> None:
    saved = tmp_path / "turns.json"
    saved.write_text(GOLDEN_LIKE, encoding="utf-8")
    getter = FakeHttpGetter({})
    arms = await lc.collect(getter, CREDENTIALS, [f"GOLD={saved}"])
    assert len(arms[0].spoken) == 1
    assert getter.urls == []
