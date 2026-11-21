"""Parses Agora's Turns API reply (per-turn latency) and renders it as a markdown table.

Live shape (2026-11-21, see VERIFIED.md): each item of `turns` has `turn_id`, `start.type`,
`end.type` and `metrics: {e2e_latency_ms, segmented_latency_ms: [{name, latency}]}`.
Parsing stays tolerant of the older flat shape.
"""

import json
import math
from collections.abc import Mapping

FIRST_COLUMNS = (
    "e2e_latency_ms",
    "asr_ttlw",
    "llm_ttft",
    "llm_ftfs",
    "tts_ttfb",
    "transport",
    "algorithm_processing",
)
type Turn = dict[str, float]


class TurnsError(Exception):
    """The Turns API could not be read. The message never contains credentials."""


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


SEGMENT_NAME_KEYS = ("name", "type", "segment")
SEGMENT_VALUE_KEYS = ("latency_ms", "latency", "value", "ms")


def _first_number(item: Mapping[str, object], keys: tuple[str, ...]) -> float | None:
    numbers = [n for key in keys if (n := _number(item.get(key))) is not None]
    return numbers[0] if numbers else None


def _named_segment(item: object) -> tuple[str, float] | None:
    """`{"name": "llm_ttft", "latency_ms": 900}` -> ("llm_ttft", 900)."""
    if not isinstance(item, Mapping):
        return None
    names = [str(item[key]) for key in SEGMENT_NAME_KEYS if item.get(key)]
    number = _first_number(item, SEGMENT_VALUE_KEYS)
    return (names[0], number) if names and number is not None else None


def _segments(raw: object) -> dict[str, float]:
    """`{"llm_ttft": 900}` or `[{"name": "llm_ttft", "latency_ms": 900}]` -> name -> ms."""
    if isinstance(raw, Mapping):
        pairs = [(str(name), _number(value)) for name, value in raw.items()]
        return {name: number for name, number in pairs if number is not None}
    if isinstance(raw, list):
        return dict(pair for item in raw if (pair := _named_segment(item)) is not None)
    return {}


def _turn_row(item: object) -> Turn | None:
    if not isinstance(item, Mapping):
        return None
    metrics = item.get("metrics")
    source: Mapping[str, object] = metrics if isinstance(metrics, Mapping) else item
    row = _segments(source.get("segmented_latency_ms"))
    e2e = _number(source.get("e2e_latency_ms", source.get("e2e_latency")))
    return row if e2e is None else {"e2e_latency_ms": e2e, **row}


def parse_turns(body: str) -> list[Turn]:
    """Each turn as column -> ms. Accepts a bare list or the list under turns/data/items."""
    try:
        parsed: object = json.loads(body)
    except ValueError as error:
        raise TurnsError(f"reply is not JSON: {body[:80]!r}") from error
    if isinstance(parsed, Mapping):
        parsed = next((parsed[k] for k in ("turns", "data", "items", "list") if k in parsed), [])
    if not isinstance(parsed, list):
        return []
    return [row for item in parsed if (row := _turn_row(item)) is not None]


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile. Example: ([1, 2, 3, 4], 0.5) -> 2."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def _cell(value: float | None) -> str:
    return "-" if value is None else f"{value:g}"


def markdown_table(turns: list[Turn]) -> str:
    """One row per turn plus p50 and p95 rows. Columns: the known ones first, then any others."""
    seen = {name for turn in turns for name in turn}
    columns = [c for c in FIRST_COLUMNS if c in seen] + sorted(seen - set(FIRST_COLUMNS))
    if not columns:
        return "No latency fields found in the turns."
    lines = ["| turn | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    for index, turn in enumerate(turns, 1):
        lines.append(f"| {index} | " + " | ".join(_cell(turn.get(c)) for c in columns) + " |")
    for label, fraction in (("p50", 0.5), ("p95", 0.95)):
        cells = [_cell(percentile([t[c] for t in turns if c in t], fraction)) for c in columns]
        lines.append(f"| **{label}** | " + " | ".join(cells) + " |")
    return "\n".join(lines)
