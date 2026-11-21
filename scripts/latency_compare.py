"""Compare Agora's per-turn latency between test arms. Run through scripts/latency-compare.sh.

Usage: latency_compare.py LABEL=AGENT_ID [LABEL=AGENT_ID ...]
       (AGENT_ID may also be a saved Turns API reply, a .json file)
Needs AGORA_APP_ID, AGORA_REST_KEY, AGORA_REST_SECRET for agent ids. Read-only.

Only `voice_input` turns that reached our backend (`llm_ttft` present) and were not interrupted are
counted. Spoken turns (`tts_ttfb` present: Mochi said something) and silent turns (hint or nothing:
an empty reply, so no TTS) are summarised apart, because their e2e covers different stages.
"""

import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mochi_backend.gateway.agora.rest_client import AgoraTurnsClient
from mochi_backend.gateway.agora.turns_client import Turn, TurnsError, parse_turns, percentile
from mochi_backend.platform.http_client import (
    HttpGetter,
    HttpResponse,
    HttpTransportError,
    HttpxClient,
)

STAGES = ("algorithm_processing", "asr_ttlw", "llm_ttft", "llm_ftfs", "tts_ttfb", "e2e_latency_ms")
SILENT_STAGES = ("algorithm_processing", "asr_ttlw", "llm_ttft", "e2e_latency_ms")
SHORT_NAMES = {"algorithm_processing": "alg_proc", "e2e_latency_ms": "e2e"}
MIN_TURNS = 10
CREDENTIAL_NAMES = ("AGORA_APP_ID", "AGORA_REST_KEY", "AGORA_REST_SECRET")
type TurnItem = Mapping[str, object]


class LastBodyGetter:
    """An `HttpGetter` that keeps the last raw reply body.

    `AgoraTurnsClient.turns()` keeps only the metrics; the turn's start and end types (needed to
    drop greetings and interrupted turns) are re-read from the same body.
    Example: `LastBodyGetter(HttpxClient())`.
    """

    def __init__(self, inner: HttpGetter) -> None:
        self._inner = inner
        self.last_body = ""

    async def get(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        """Delegate, then remember the body."""
        reply = await self._inner.get(url, headers, timeout_seconds)
        self.last_body = reply.body
        return reply


@dataclass(frozen=True)
class ArmTurns:
    """The kept turns of one arm. `skipped` counts every turn that was not kept."""

    label: str
    spoken: list[Turn]
    silent: list[Turn]
    skipped: int


def turn_items(body: str) -> list[TurnItem]:
    """The raw turn objects of a Turns API reply (`{"turns": [...]}` or a bare list)."""
    if not body.strip():
        return []
    parsed: object = json.loads(body)
    if isinstance(parsed, Mapping):
        parsed = parsed.get("turns", [])
    return (
        [item for item in parsed if isinstance(item, Mapping)] if isinstance(parsed, list) else []
    )


def _kind(item: TurnItem, edge: str) -> str:
    block = item.get(edge)
    return str(block.get("type", "")) if isinstance(block, Mapping) else ""


def is_measured_voice_turn(item: TurnItem, row: Turn) -> bool:
    """A spoken sentence that reached our backend and was not interrupted.

    Example: a greeting, an `api_speak` line or a turn ended by `interrupted` gives False.
    """
    started_by_voice = _kind(item, "start") == "voice_input"
    return started_by_voice and "llm_ttft" in row and _kind(item, "end") != "interrupted"


def arm_turns(label: str, body: str) -> ArmTurns:
    """Split one Turns API reply into kept spoken turns, kept silent turns and skipped ones."""
    items = turn_items(body)
    rows = parse_turns(json.dumps(items))  # same order: every item is a mapping
    kept = [row for item, row in zip(items, rows, strict=True) if is_measured_voice_turn(item, row)]
    spoken = [row for row in kept if "tts_ttfb" in row]
    silent = [row for row in kept if "tts_ttfb" not in row]
    return ArmTurns(label, spoken, silent, len(items) - len(kept))


def session_minutes(body: str) -> float | None:
    """Minutes from the first turn's `start_at` to the last turn's `end_at` (epoch ms), if known."""
    starts, ends = [], []
    for item in turn_items(body):
        start, end = item.get("start"), item.get("end")
        if isinstance(start, Mapping) and isinstance(start.get("start_at"), int | float):
            starts.append(float(start["start_at"]))
        if isinstance(end, Mapping) and isinstance(end.get("end_at"), int | float):
            ends.append(float(end["end_at"]))
    if not starts or not ends:
        return None
    return max(0.0, max(ends) - min(starts)) / 60000.0


def _stats(turns: list[Turn], stage: str) -> tuple[float | None, float | None]:
    values = [turn[stage] for turn in turns if stage in turn]
    return percentile(values, 0.5), percentile(values, 0.95)


def _ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def _delta(value: float | None, base: float | None) -> str:
    return "-" if value is None or base is None else f"{value - base:+.0f}"


def _header(stages: Sequence[str]) -> list[str]:
    names = [SHORT_NAMES.get(stage, stage) for stage in stages]
    return ["| arm | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(stages)]


def stats_table(arms: list[ArmTurns], spoken: bool) -> str:
    """Per arm: n, then `p50 / p95` in ms for every stage."""
    stages = STAGES if spoken else SILENT_STAGES
    lines = _header(stages)
    for arm in arms:
        turns = arm.spoken if spoken else arm.silent
        cells = [" / ".join(_ms(v) for v in _stats(turns, stage)) for stage in stages]
        lines.append(f"| {arm.label} | {len(turns)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def delta_table(arms: list[ArmTurns], spoken: bool) -> str:
    """Per arm after the first: `Δp50 / Δp95` in ms against the first arm (negative is faster)."""
    stages = STAGES if spoken else SILENT_STAGES
    base = arms[0].spoken if spoken else arms[0].silent
    lines = _header(stages)
    for arm in arms[1:]:
        turns = arm.spoken if spoken else arm.silent
        cells = []
        for stage in stages:
            (p50, p95), (b50, b95) = _stats(turns, stage), _stats(base, stage)
            cells.append(f"{_delta(p50, b50)} / {_delta(p95, b95)}")
        lines.append(f"| {arm.label} | {len(turns)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def small_sample_warnings(arms: list[ArmTurns]) -> list[str]:
    """One line per arm with fewer than `MIN_TURNS` spoken turns."""
    return [
        f"WARNING: {arm.label} has only {len(arm.spoken)} spoken turns (< {MIN_TURNS}); "
        "its p95 is just its slowest turn"
        for arm in arms
        if len(arm.spoken) < MIN_TURNS
    ]


def report(arms: list[ArmTurns]) -> str:
    """The whole markdown report: spoken and silent tables, deltas vs the first arm, warnings."""
    first = arms[0].label
    parts = [
        "## Spoken turns (p50 / p95 ms)",
        stats_table(arms, spoken=True),
        "## Silent turns: hint or nothing (p50 / p95 ms)",
        stats_table(arms, spoken=False),
    ]
    if len(arms) > 1:
        parts += [f"## Spoken turns vs {first} (ms)", delta_table(arms, spoken=True)]
        parts += [f"## Silent turns vs {first} (ms)", delta_table(arms, spoken=False)]
    skipped = ", ".join(f"{arm.label} {arm.skipped}" for arm in arms)
    parts.append(f"Not counted (greeting, api_speak, interrupted, no LLM): {skipped}")
    return "\n\n".join(parts + small_sample_warnings(arms))


def parse_arm_spec(spec: str) -> tuple[str, str]:
    """`"PROD=A46AF..."` -> ("PROD", "A46AF..."). Raises ValueError on another shape."""
    label, sep, source = spec.partition("=")
    if not sep or not label or not source:
        raise ValueError(f"arm {spec!r}: expected LABEL=AGENT_ID or LABEL=turns.json")
    return label, source


async def fetch_body(getter: HttpGetter, credentials: tuple[str, str, str], source: str) -> str:
    """The raw Turns API reply for an agent id, or the content of a saved reply file."""
    if source.endswith(".json") and Path(source).is_file():
        return Path(source).read_text(encoding="utf-8")
    recorder = LastBodyGetter(getter)
    client = AgoraTurnsClient(recorder, *credentials)
    if not await client.turns(source):
        return ""  # 404 while the agent runs, or no turns: Agora has nothing to give yet
    return recorder.last_body


async def collect(
    getter: HttpGetter, credentials: tuple[str, str, str], specs: list[str]
) -> list[ArmTurns]:
    """Fetch every arm (in order) and split its turns."""
    pairs = [parse_arm_spec(spec) for spec in specs]
    bodies = [await fetch_body(getter, credentials, source) for _, source in pairs]
    return [arm_turns(label, body) for (label, _), body in zip(pairs, bodies, strict=True)]


def credentials_from_env() -> tuple[str, str, str]:
    """(app id, REST key, REST secret) from the environment; empty strings when unset."""
    app_id, key, secret = (os.environ.get(name, "") for name in CREDENTIAL_NAMES)
    return app_id, key, secret


def main(argv: list[str]) -> int:
    """Print the comparison; returns the exit code."""
    specs = argv[1:]
    if not specs:
        print(__doc__)
        return 2
    missing = [name for name in CREDENTIAL_NAMES if not os.environ.get(name)]
    try:
        arms = asyncio.run(collect(HttpxClient(), credentials_from_env(), specs))
    except (TurnsError, HttpTransportError, ValueError) as error:
        print(f"could not compare: {error} (missing env: {missing})")
        return 1
    print(report(arms))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
