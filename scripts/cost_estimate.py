"""Estimate one test session's cost per arm, and per 10-minute demo. Run: scripts/cost-estimate.sh.

Usage: cost_estimate.py [--prices FILE] ARM [ARM ...]
  ARM = LABEL,ASR,TTS,DURATION[,LOG]
    ASR      openai | ares                 (openai adds OpenAI transcription per audio minute)
    TTS      minimax | cartesia
    DURATION minutes (e.g. 6.5), an agent id (minutes from its Agora turns: first start to last
             end, a lower bound on the billed time), or a saved Turns API reply (.json)
    LOG      the backend log of that run (.local/latency/<preset>-*.log) or - for stdin; its
             `model_usage` lines give the model tokens. With an agent id only that session counts.
Prices: config/prices.json (each entry has its source and verified flag). The first 300 Agora
minutes each month are free; this prints list prices.
"""

import asyncio
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from latency_compare import credentials_from_env, fetch_body, session_minutes
from pydantic import BaseModel, ConfigDict, ValidationError

from mochi_backend.gateway.agora.turns_client import TurnsError
from mochi_backend.platform.http_client import HttpGetter, HttpTransportError, HttpxClient

PRICES_FILE = Path(__file__).resolve().parents[1] / "config" / "prices.json"
DEMO_MINUTES = 10.0
TOKENS_PER_PRICE_UNIT = 1_000_000
type LogRecord = Mapping[str, object]


class PriceSource(BaseModel):
    """Where a price comes from, and whether a current public page confirmed it."""

    model_config = ConfigDict(extra="ignore")
    source: str
    verified: bool
    note: str = ""


class MinutePrice(PriceSource):
    """A price per minute of session audio."""

    per_minute: float


class ModelPrice(PriceSource):
    """OpenAI token prices per million tokens."""

    input_per_mtok: float
    cached_input_per_mtok: float
    output_per_mtok: float


class PriceTable(BaseModel):
    """config/prices.json."""

    model_config = ConfigDict(extra="ignore")
    agora_audio_task: MinutePrice
    transcription_per_minute: dict[str, MinutePrice]
    tts_per_minute: dict[str, MinutePrice]
    models: dict[str, ModelPrice]


class ModelUsage(BaseModel):
    """One `model_usage` log line of the backend."""

    model_config = ConfigDict(extra="ignore")
    model: str
    kind: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0  # part of prompt_tokens, billed at the cached rate


@dataclass(frozen=True)
class ArmSpec:
    """One arm from the command line."""

    label: str
    asr: str
    tts: str
    duration: str
    log: str


@dataclass(frozen=True)
class ArmCost:
    """The estimate for one session of one arm (US dollars)."""

    label: str
    minutes: float
    agora: float
    transcription: float
    tts: float
    models: float
    model_calls: int
    unpriced_models: tuple[str, ...]
    hedges: int
    hedge_estimate: float
    unverified: tuple[str, ...]

    @property
    def total(self) -> float:
        """Everything priced, without the hedge estimate (a hedge's losing call is not logged)."""
        return self.agora + self.transcription + self.tts + self.models


def load_prices(path: Path) -> PriceTable:
    """Read and validate the price table."""
    return PriceTable.model_validate_json(path.read_text(encoding="utf-8"))


def parse_arm(spec: str) -> ArmSpec:
    """`"PROD,openai,minimax,6.5,prod.log"` -> ArmSpec. Raises ValueError on another shape."""
    parts = spec.split(",")
    if len(parts) not in (4, 5) or not all(parts[:4]):
        raise ValueError(f"arm {spec!r}: expected LABEL,ASR,TTS,DURATION[,LOG]")
    label, asr, tts, duration, *log = parts
    return ArmSpec(label, asr, tts, duration, log[0] if log else "")


def log_records(lines: Iterable[str]) -> list[LogRecord]:
    """The JSON objects among the log lines; anything else (uvicorn's text) is skipped."""
    records: list[LogRecord] = []
    for line in lines:
        start = line.find("{")
        try:
            parsed: object = json.loads(line[start:]) if start >= 0 else None
        except ValueError:
            continue
        if isinstance(parsed, Mapping):
            records.append(parsed)
    return records


def session_records(records: list[LogRecord], agent_id: str) -> list[LogRecord]:
    """Lines from that agent's `agent_started` to the next one; all lines when no id is given."""
    if not agent_id:
        return records
    starts = [i for i, r in enumerate(records) if r.get("event") == "agent_started"]
    mine = [i for i in starts if records[i].get("agent_id") == agent_id]
    if not mine:
        return []
    later = [i for i in starts if i > mine[0]]
    return records[mine[0] : later[0] if later else len(records)]


def usages(records: list[LogRecord]) -> list[ModelUsage]:
    """The `model_usage` lines that parse; a malformed one is skipped."""
    found: list[ModelUsage] = []
    for record in records:
        if record.get("event") != "model_usage":
            continue
        try:
            found.append(ModelUsage.model_validate(record))
        except ValidationError:
            continue
    return found


def hedge_count(records: list[LogRecord]) -> int:
    """How often the character call was asked twice (`character_hedge_used`, event or flag)."""
    return sum(
        1
        for r in records
        if r.get("event") == "character_hedge_used" or r.get("character_hedge_used") is True
    )


def model_price(prices: PriceTable, model: str) -> ModelPrice | None:
    """The price of `model`, also for dated names ("gpt-5.4-mini-2026-03-17" -> "gpt-5.4-mini")."""
    names = sorted((n for n in prices.models if model.startswith(n)), key=len, reverse=True)
    return prices.models[names[0]] if names else None


def call_cost(usage: ModelUsage, price: ModelPrice) -> float:
    """Dollars for one call: uncached input, cached input and output at their own rates."""
    cached = min(usage.cached_tokens, usage.prompt_tokens)
    dollars = (usage.prompt_tokens - cached) * price.input_per_mtok
    dollars += (
        cached * price.cached_input_per_mtok + usage.completion_tokens * price.output_per_mtok
    )
    return dollars / TOKENS_PER_PRICE_UNIT


def _priced_calls(calls: list[ModelUsage], prices: PriceTable) -> list[tuple[ModelUsage, float]]:
    pairs = [(call, model_price(prices, call.model)) for call in calls]
    return [(call, call_cost(call, price)) for call, price in pairs if price is not None]


def _vendor(table: Mapping[str, MinutePrice], name: str, what: str) -> MinutePrice:
    if name not in table:
        raise ValueError(f"{what} {name!r} has no price; expected one of {sorted(table)}")
    return table[name]


def arm_cost(
    spec: ArmSpec, minutes: float, records: list[LogRecord], prices: PriceTable
) -> ArmCost:
    """Price one session: Agora minutes, transcription, voice, model tokens, hedge estimate."""
    asr = _vendor(prices.transcription_per_minute, spec.asr, "ASR")
    tts = _vendor(prices.tts_per_minute, spec.tts, "TTS")
    calls = usages(records)
    priced = _priced_calls(calls, prices)
    character = [cost for call, cost in priced if call.kind == "character"]
    hedges = hedge_count(records)
    unverified = [
        name for name, p in ((f"{spec.asr} ASR", asr), (f"{spec.tts} TTS", tts)) if not p.verified
    ]
    return ArmCost(
        label=spec.label,
        minutes=minutes,
        agora=minutes * prices.agora_audio_task.per_minute,
        transcription=minutes * asr.per_minute,
        tts=minutes * tts.per_minute,
        models=sum(cost for _, cost in priced),
        model_calls=len(calls),
        unpriced_models=tuple(
            sorted({c.model for c in calls if model_price(prices, c.model) is None})
        ),
        hedges=hedges,
        hedge_estimate=hedges * (sum(character) / len(character) if character else 0.0),
        unverified=tuple(unverified),
    )


def _usd(value: float) -> str:
    return f"${value:.4f}"


def _flags(arm: ArmCost) -> str:
    flags = [f"UNVERIFIED: {name} billing" for name in arm.unverified]
    flags += [f"UNPRICED model: {name}" for name in arm.unpriced_models]
    return "; ".join(flags) or "-"


def report(arms: list[ArmCost]) -> str:
    """Markdown: one row per arm, per session and scaled to a 10-minute demo."""
    lines = [
        "| arm | minutes | Agora | transcription | TTS | models (calls) | per session | per 10 min "
        "| hedges (est. extra) | flags |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm in arms:
        per_demo = arm.total * DEMO_MINUTES / arm.minutes if arm.minutes > 0 else 0.0
        lines.append(
            f"| {arm.label} | {arm.minutes:.1f} | {_usd(arm.agora)} | {_usd(arm.transcription)} "
            f"| {_usd(arm.tts)} | {_usd(arm.models)} ({arm.model_calls}) | {_usd(arm.total)} "
            f"| {_usd(per_demo)} | {arm.hedges} ({_usd(arm.hedge_estimate)}) | {_flags(arm)} |"
        )
    lines.append(
        "\nList prices; the first 300 Agora minutes each month are free. Per 10 min scales the "
        "session linearly. Hedges: the losing call of a hedge is cancelled and writes no "
        "model_usage line, so its cost is NOT in the totals; the estimate (hedges x mean "
        "character call) is an upper bound, as a cancelled call may be billed only in part."
    )
    return "\n".join(lines)


def _read_log(path: str) -> list[str]:
    if not path:
        return []
    if path == "-":
        return sys.stdin.read().splitlines()
    return Path(path).read_text(encoding="utf-8").splitlines()


async def resolve_minutes(getter: HttpGetter, duration: str) -> tuple[float, str]:
    """(minutes, agent id or ""): a number is minutes; otherwise read the agent's turns."""
    try:
        return float(duration), ""
    except ValueError:
        pass
    body = await fetch_body(getter, credentials_from_env(), duration)
    minutes = session_minutes(body)
    if minutes is None:
        raise ValueError(f"no turns with times for {duration!r}; pass the minutes instead")
    agent_id = "" if duration.endswith(".json") else duration
    return minutes, agent_id


async def estimate(getter: HttpGetter, specs: list[str], prices: PriceTable) -> list[ArmCost]:
    """Every arm's cost, in the order given."""
    costs = []
    for spec in map(parse_arm, specs):
        minutes, agent_id = await resolve_minutes(getter, spec.duration)
        records = session_records(log_records(_read_log(spec.log)), agent_id)
        costs.append(arm_cost(spec, minutes, records, prices))
    return costs


def main(argv: list[str]) -> int:
    """Print the estimate; returns the exit code."""
    args = argv[1:]
    path = PRICES_FILE
    if args[:1] == ["--prices"] and len(args) > 1:
        path, args = Path(args[1]), args[2:]
    if not args:
        print(__doc__)
        return 2
    try:
        costs = asyncio.run(estimate(HttpxClient(), args, load_prices(path)))
    except (ValueError, OSError, HttpTransportError, TurnsError) as error:
        print(f"could not estimate: {error}")
        return 1
    print(report(costs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
