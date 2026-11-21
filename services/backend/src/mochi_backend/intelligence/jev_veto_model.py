"""A parallel veto in front of nothing: JEV may block a hint, never create or change one."""

import asyncio
import time

from mochi_backend.intelligence.jev_client import JevClient, JevScores
from mochi_backend.intelligence.model_port import HintModel, ModelRequest, ModelSuggestion
from mochi_backend.platform.http_client import JsonValue
from mochi_backend.platform.json_logging import EventLogger

FIELD_CAP = 200  # characters per field of the state
RECENT_TURNS = 3
SERIOUS_VETO = 0.7
# 0.0 = never veto on "not stuck": JEV reads "stuck" literally, so a clean code switch scores
# about 0.1-0.3 and the live eval lost 5 real hints at 0.15. The veto is for serious talk only.
STUCK_VETO = 0.0
BUDGET_SECONDS = 0.5  # the most the hint waits for JEV once the hint model has answered

type Timed = tuple[JevScores | None, float]


def jev_state(request: ModelRequest) -> dict[str, JsonValue]:
    """Short structured state: speech only in string values. Example: `jev_state(req)["focus"]`."""
    recent: list[JsonValue] = [t[:FIELD_CAP] for t in request.recent_texts[-RECENT_TURNS:]]
    return {"focus": request.focus.value, "recent": recent, "sentence": request.text[:FIELD_CAP]}


async def _timed(jev: JevClient, state: dict[str, JsonValue]) -> Timed:
    start = time.monotonic()
    scores = await jev.judge(state)
    return scores, (time.monotonic() - start) * 1000


class JevVetoHintModel:
    """Implements `HintModel`. Example: `JevVetoHintModel(inner, jev).logging(logger)`.

    Runs `inner` and JEV together. Only a SHOW_HINT can be vetoed, and only to IGNORE.
    The hedge in `decision_flow` asks twice for one request; both asks share one JEV call.
    """

    def __init__(
        self,
        inner: HintModel,
        jev: JevClient,
        budget_seconds: float = BUDGET_SECONDS,
        serious_veto: float = SERIOUS_VETO,
        stuck_veto: float = STUCK_VETO,
    ) -> None:
        self._inner = inner
        self._jev = jev
        self._budget = budget_seconds
        self._serious_veto = serious_veto
        self._stuck_veto = stuck_veto
        self._logger: EventLogger | None = None
        self._shared: tuple[ModelRequest, asyncio.Task[Timed]] | None = None

    def logging(self, logger: EventLogger) -> "JevVetoHintModel":
        """Log one metadata-only line per judged hint, and return self."""
        self._logger = logger
        return self

    def _jev_task(self, request: ModelRequest) -> "asyncio.Task[Timed]":
        if self._shared is not None and self._shared[0] is request:
            return self._shared[1]
        task = asyncio.ensure_future(_timed(self._jev, jev_state(request)))
        self._shared = (request, task)
        return task

    def _vetoes(self, scores: JevScores) -> bool:
        return scores.serious >= self._serious_veto or scores.stuck < self._stuck_veto

    async def _stop(self, task: "asyncio.Task[Timed]") -> None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)  # nothing left running or unread

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """The inner answer, or IGNORE when it was a hint JEV judges serious or not a stuck word."""
        jev = self._jev_task(request)
        try:
            answer = await self._inner.suggest(request)
        except BaseException:
            await self._stop(jev)
            raise
        if answer is None or answer.decision != "SHOW_HINT":
            await self._stop(jev)  # nothing to veto: do not wait for JEV
            return answer
        waited = time.monotonic()
        await asyncio.wait({jev}, timeout=self._budget)
        if not jev.done():
            await self._stop(jev)
            return self._verdict(answer, None, (time.monotonic() - waited) * 1000)
        if jev.cancelled() or jev.exception() is not None:
            return self._verdict(answer, None, (time.monotonic() - waited) * 1000)
        scores, millis = jev.result()
        return self._verdict(answer, scores, millis)

    def _verdict(
        self, answer: ModelSuggestion, scores: JevScores | None, millis: float
    ) -> ModelSuggestion:
        vetoed = scores is not None and self._vetoes(scores)
        if self._logger is not None:
            self._logger.log(
                "jev_veto",
                {
                    "jev_latency_ms": round(millis),
                    "jev_serious": scores.serious if scores else None,
                    "jev_stuck": scores.stuck if scores else None,
                    "vetoed": vetoed,
                },
            )
        return ModelSuggestion(decision="IGNORE") if vetoed else answer
