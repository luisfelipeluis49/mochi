"""Clock formatting, ids, scheduler fake, JSON logging."""

import json
import logging
from datetime import UTC, datetime

from mochi_backend.platform.clock import iso_z, parse_iso_z
from mochi_backend.platform.ids import SequentialIdGenerator, UuidIdGenerator
from mochi_backend.platform.json_logging import JsonFormatter, StdlibEventLogger
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_scheduler import FakeScheduler


def test_iso_z_matches_the_contract_format() -> None:
    moment = datetime(2026, 11, 19, 16, 0, 4, 700000, tzinfo=UTC)
    assert iso_z(moment) == "2026-11-19T16:00:04.700Z"


def test_parse_iso_z_round_trips() -> None:
    assert iso_z(parse_iso_z("2026-11-19T16:00:04.700Z")) == "2026-11-19T16:00:04.700Z"


def test_uuid_ids_are_prefixed_and_unique() -> None:
    ids = UuidIdGenerator()
    first, second = ids.new("evt"), ids.new("evt")
    assert first.startswith("evt_") and first != second


def test_sequential_ids_are_predictable() -> None:
    ids = SequentialIdGenerator()
    assert [ids.new("hint"), ids.new("learn")] == ["hint_001", "learn_002"]


async def test_scheduler_runs_only_due_uncancelled_callbacks() -> None:
    clock, ran = FakeClock(), []
    scheduler = FakeScheduler(clock)

    async def mark() -> None:
        ran.append(clock.now())

    scheduler.call_later(8, mark)
    cancelled = scheduler.call_later(1, mark)
    cancelled.cancel()
    assert await scheduler.run_due() == 0
    clock.advance(8)
    assert await scheduler.run_due() == 1
    assert len(ran) == 1


def test_json_logger_writes_one_json_object_with_fields() -> None:
    records: list[str] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(self.format(record))

    logger = logging.getLogger("mochi.test_platform")
    sink = Collect()
    sink.setFormatter(JsonFormatter())
    logger.handlers, logger.propagate = [sink], False
    logger.setLevel(logging.INFO)
    StdlibEventLogger(logger).log("turn", {"text_len": 12})
    assert json.loads(records[0]) == {"level": "INFO", "event": "turn", "text_len": 12}
