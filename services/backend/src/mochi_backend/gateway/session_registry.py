"""The live sessions, each with its own state, so a phone never disturbs the Pi (DECISIONS D-37).

A session is everything one conversation needs: its store, hub view, live hint, silence policy,
turn pipeline, game and Agora agent. The demo session (the Pi's) always exists. Any other id is
opened by its first Start and forgotten at its Stop.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from mochi_backend.gateway.activity_service import ActivityService
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.demo_reset import DemoReset
from mochi_backend.gateway.errors import ConflictError, NotFoundError
from mochi_backend.gateway.roster import SESSION_ID
from mochi_backend.gateway.session_service import SessionService
from mochi_backend.gateway.turn_pipeline import TurnPipeline

SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,40}$"
MAX_SESSIONS = 8  # each live one holds an Agora agent, which costs money


@dataclass(frozen=True)
class SessionRuntime:
    """One session's parts. Example: `registry.open("p-1").sessions.start()`."""

    session_id: str
    core: GatewayCore
    pipeline: TurnPipeline
    sessions: SessionService
    activity: ActivityService
    demo_reset: DemoReset


class SessionRegistry:
    """Maps a session id to its runtime. The demo session cannot be closed."""

    def __init__(
        self,
        demo: SessionRuntime,
        build: Callable[[str], SessionRuntime],
        limit: int = MAX_SESSIONS,
    ) -> None:
        self._live: dict[str, SessionRuntime] = {SESSION_ID: demo}
        self._build = build
        self._limit = limit

    @staticmethod
    def is_valid_id(session_id: str) -> bool:
        """Example: `is_valid_id("p-1")` is True; `is_valid_id("a/b")` is False."""
        return re.fullmatch(SESSION_ID_PATTERN, session_id) is not None

    def peek(self, session_id: str) -> SessionRuntime | None:
        """The session if it exists, else None."""
        return self._live.get(session_id)

    def runtime(self, session_id: str) -> SessionRuntime:
        """The session; `NotFoundError` (404) when nobody started it."""
        found = self._live.get(session_id)
        if found is None:
            raise NotFoundError(f"unknown session {session_id!r}; start it first")
        return found

    def open(self, session_id: str) -> SessionRuntime:
        """The session, created if new. `ConflictError` (409) when too many are live."""
        found = self._live.get(session_id)
        if found is not None:
            return found
        if len(self._live) >= self._limit:
            raise ConflictError(f"{self._limit} sessions are live; stop one first")
        self._live[session_id] = self._build(session_id)
        return self._live[session_id]

    def close(self, session_id: str) -> None:
        """Forget a stopped session (the demo session stays)."""
        if session_id != SESSION_ID:
            self._live.pop(session_id, None)

    def live_ids(self) -> list[str]:
        """Ids of the sessions that exist now."""
        return list(self._live)
