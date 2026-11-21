"""Turns Agora gave up on: a newer request, or a closed connection, cancels the older decide().

Golden data (2026-11-21): a turn waited ~400 ms behind turns Agora had already abandoned, whose
model calls still ran 1.1-1.9 s. With `MOCHI_CANCEL_STALE_TURNS=true` a newer request for the
session cancels the decide() of every older one still deciding; one still waiting for its turn
is skipped. Only the deciding is ever cancelled: nothing is applied or published before the
commit, so a cancelled turn leaves no learning event, hint or history behind (DECISIONS D-37).
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass, field

from mochi_backend.gateway.spoken_release import SpokenOutlet
from mochi_contracts import Decision

Gone = Callable[[], Awaitable[object]]  # returns once the caller has hung up


def _nothing_said() -> bool:
    return False


@dataclass
class Ticket:
    """One request's place in line. `gone`: how to tell the caller hung up.

    `spoken`: True once part of its reply has gone out; it is never cancelled after that.
    """

    number: int
    gone: Gone | None = None
    spoken: Callable[[], bool] = _nothing_said
    deciding: "asyncio.Future[Decision] | None" = None
    why: str | None = field(default=None)  # set when cancelled: "superseded" or "disconnected"
    outlet: SpokenOutlet | None = None  # where its reply streams (MOCHI_STREAM_REPLY), if it may


class StaleTurns:
    """Example: `ticket = stale.arrive()`, then `await stale.decide(ticket, work)` (None = dropped).

    Disabled, `decide` only awaits the work and `is_stale` is always False: today's behaviour.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._latest = 0
        self._open: dict[int, Ticket] = {}

    def arrive(
        self, gone: Gone | None = None, spoken: Callable[[], bool] = _nothing_said
    ) -> Ticket:
        """A new request: every older one still deciding is cancelled (when enabled)."""
        self._latest += 1
        ticket = Ticket(self._latest, gone, spoken)
        if self.enabled:
            for older in list(self._open.values()):
                self._cancel(older, "superseded")
        self._open[ticket.number] = ticket
        return ticket

    def is_stale(self, ticket: Ticket) -> bool:
        """True when a newer request came while this one waited for its turn."""
        return self.enabled and ticket.number != self._latest

    def leave(self, ticket: Ticket) -> None:
        """The request is done (answered or dropped)."""
        self._open.pop(ticket.number, None)

    def _cancel(self, ticket: Ticket, why: str) -> None:
        if ticket.spoken() or ticket.deciding is None or ticket.deciding.done():
            return
        ticket.why = why
        ticket.deciding.cancel()

    async def decide(
        self, ticket: Ticket, work: Coroutine[None, None, Decision]
    ) -> Decision | None:
        """The work's decision, or None when it was cancelled as stale.

        A cancel of the request itself (not of its deciding) is passed on, never swallowed.
        """
        if not self.enabled:
            return await work
        ticket.deciding = asyncio.ensure_future(work)
        watcher = asyncio.ensure_future(self._watch(ticket)) if ticket.gone else None
        try:
            await asyncio.wait({ticket.deciding})
        finally:
            ticket.deciding.cancel()  # a no-op once done; stops it when the request is cancelled
            if watcher is not None:
                watcher.cancel()
        return None if ticket.deciding.cancelled() else ticket.deciding.result()

    async def _watch(self, ticket: Ticket) -> None:
        if ticket.gone is None:
            return
        await ticket.gone()
        self._cancel(ticket, "disconnected")
