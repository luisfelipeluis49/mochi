"""The one session's in-memory state (no database, AGENTS 8)."""

from datetime import datetime

from mochi_backend.gateway.roster import DEMO_PARTICIPANTS, SESSION_ID, USER_IDS
from mochi_contracts import (
    Activity,
    GameState,
    Hint,
    Language,
    LearningEvent,
    SessionContext,
    SessionMode,
    SessionState,
    SessionStatus,
    Turn,
)

HISTORY_LIMIT = 5


def idle_activity() -> Activity:
    """The IDLE game state (round fields null; see DECISIONS D-03)."""
    return Activity(
        activity_id="describe_and_guess",
        round_id=None,
        state=GameState.IDLE,
        describer_user_id=None,
        guesser_user_id=None,
        public_instruction=None,
        result=None,
        revealed_word=None,
        word_source=None,
    )


class SessionStore:
    """Status, mode, agent id, game state and the last few turns and hints."""

    def __init__(self) -> None:
        self.status = SessionStatus.CREATED
        self.mode = SessionMode.TOGETHER
        self.capturing = False
        self.agent_id: str | None = None
        # True while the device runs the agent itself: we started none, and it does the talking.
        self.agent_on_device = False
        self.pi_token: str | None = None
        self.pi_token_expires_at: datetime | None = None
        self.activity: Activity = idle_activity()
        self.turns: list[Turn] = []
        self.hints: list[Hint] = []
        self.generation = 0

    def invalidate(self) -> None:
        """Mark everything in flight (a pending start or turn) as out of date.

        Stop and Reset call this synchronously; work that began earlier compares `generation`
        before it changes anything and drops itself when it differs.
        """
        self.generation += 1

    def end_game(self) -> None:
        """Back to IDLE and `together` without touching history (used by Stop)."""
        self.activity = idle_activity()
        self.mode = SessionMode.TOGETHER

    def session_state(self) -> SessionState:
        """The `session.state.changed` payload."""
        return SessionState(
            status=self.status,
            mode=self.mode,
            focus=Language.EN,
            capturing=self.capturing,
            participants=list(USER_IDS),
        )

    def context(self, words: dict[str, list[LearningEvent]]) -> SessionContext:
        """What intelligence may look at: last 5 turns and hints, the game, saved words."""
        playing = self.activity if self.activity.state is not GameState.IDLE else None
        return SessionContext(
            session_id=SESSION_ID,
            mode=self.mode,
            focus=Language.EN,
            participants=list(DEMO_PARTICIPANTS),
            recent_turns=self.turns[-HISTORY_LIMIT:],
            recent_hints=self.hints[-HISTORY_LIMIT:],
            activity=playing,
            learning_events=words,
        )

    def remember(self, turn: Turn, hint: Hint | None) -> None:
        """Append a handled turn (and its hint, if any) to the history."""
        self.turns = [*self.turns, turn][-HISTORY_LIMIT:]
        if hint is not None:
            self.hints = [*self.hints, hint][-HISTORY_LIMIT:]

    def clear_history(self) -> None:
        """Forget turns, hints and the game (keeps capturing as it is)."""
        self.turns, self.hints = [], []
        self.end_game()
