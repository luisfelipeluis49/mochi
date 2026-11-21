"""TypeSafe JEV: a judge that scores yes/no statements about a text. It cannot write anything."""

import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from mochi_backend.platform.http_client import HTTP_OK, HttpClient, JsonValue
from mochi_backend.platform.json_logging import EventLogger

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-1.14.0"  # pinned: a moving alias would change the scores under us
# Static, single, literal statements where true means yes. Speech goes only in the state values.
SERIOUS = (
    "The conversation is about something serious or personal such as health, grief or conflict."
)
STUCK = "The speaker is stuck on, or asking for, a word or short expression."
QUESTIONS: dict[str, JsonValue] = {
    "serious": {"type": "noul", "instructions": SERIOUS},
    "stuck": {"type": "noul", "instructions": STUCK},
}


@dataclass(frozen=True)
class JevScores:
    """Probabilities 0..1 that each statement is true."""

    serious: float
    stuck: float


class JevClient(Protocol):
    """Scores one state. Returns None on any failure."""

    async def judge(self, state: dict[str, JsonValue]) -> JevScores | None:
        """Example: `await client.judge({"focus": "en", "recent": [], "sentence": "..."})`."""
        ...


class _Noul(BaseModel):
    noul: float


class _Answers(BaseModel):
    serious: _Noul
    stuck: _Noul


class _Reply(BaseModel):
    answers: _Answers


class HttpJevClient:
    """JevClient over the project's HttpClient. Example: `HttpJevClient(HttpxClient(), key)`."""

    def __init__(self, http: HttpClient, api_key: str, timeout_seconds: float = 2.0) -> None:
        self._http = http
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._logger: EventLogger | None = None

    def logging(self, logger: EventLogger) -> "HttpJevClient":
        """Log a metadata-only line when a call fails, and return self."""
        self._logger = logger
        return self

    def _failed(self, why: str) -> None:
        if self._logger is not None:
            self._logger.log("jev_failed", {"why": why})

    async def judge(self, state: dict[str, JsonValue]) -> JevScores | None:
        """Ask JEV; None on transport error, non-200 or an unreadable reply (never the body)."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload: JsonValue = {"model": JEV_MODEL, "state": state, "questions": QUESTIONS}
        try:
            reply = await self._http.post_json(JEV_URL, headers, payload, self._timeout)
            if reply.status != HTTP_OK:
                self._failed(f"status {reply.status}")
                return None
            noul = _Reply.model_validate(json.loads(reply.body)).answers
        except Exception as error:  # noqa: BLE001 - a veto that fails must leave the hint alone
            self._failed(type(error).__name__)
            return None
        return JevScores(serious=noul.serious.noul, stuck=noul.stuck.noul)
