"""Structured JSON logging on the stdlib logger (one JSON object per line)."""

import json
import logging
from collections.abc import Mapping
from typing import Protocol

JsonScalar = str | int | float | bool | None
_RESERVED = {"msg", "args", "levelname", "name", "created", "exc_info", "message"}


class EventLogger(Protocol):
    """Logs one named event with flat scalar fields. Never pass secrets."""

    def log(self, event: str, fields: Mapping[str, JsonScalar]) -> None:
        """Write one log line for `event`."""
        ...


class JsonFormatter(logging.Formatter):
    """Formats a record as JSON, merging the `fields` extra."""

    def format(self, record: logging.LogRecord) -> str:
        """Return the record as a single JSON line."""
        fields: Mapping[str, JsonScalar] = getattr(record, "fields", {})
        body = {"level": record.levelname, "event": record.getMessage(), **fields}
        return json.dumps(body, default=str, sort_keys=True)


class StdlibEventLogger:
    """EventLogger over `logging`. Example: `log("turn", {"text_len": 12})`."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def log(self, event: str, fields: Mapping[str, JsonScalar]) -> None:
        """Emit `event` at INFO (ERROR when fields carry `error`)."""
        level = logging.ERROR if "error" in fields else logging.INFO
        self._logger.log(level, event, extra={"fields": dict(fields)})


def configure_json_logging(level: str) -> StdlibEventLogger:
    """Install the JSON formatter on the `mochi` logger and return a wrapper."""
    logger = logging.getLogger("mochi")
    stream_output = logging.StreamHandler()
    stream_output.setFormatter(JsonFormatter())
    logger.handlers = [stream_output]
    logger.setLevel(level.upper())
    logger.propagate = False
    return StdlibEventLogger(logger)
