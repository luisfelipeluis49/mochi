"""The one session's in-memory state. Saved words and voices live in storage (D-32), not here."""

from datetime import datetime

from mochi_backend.gateway.device_commands import COMMAND_LIFETIME, QUEUE_LIMIT, DeviceCommand
from mochi_backend.gateway.roster import DEMO_PARTICIPANTS, SESSION_ID
from mochi_contracts import (
    Activity,
    GameState,
    Hint,
    Language,
    LearningEvent,
    Participant,
    PrivatePrompt,
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
        self.pi_token: str | None = None
        self.pi_token_expires_at: datetime | None = None
        self.activity: Activity = idle_activity()
        self.turns: list[Turn] = []
        self.hints: list[Hint] = []
        self.commands: list[DeviceCommand] = []  # for the device, newest last (this session's)
        self.round_secrets: tuple[str, ...] = ()  # the word (and its meaning) of the live round
        self.private_prompt: PrivatePrompt | None = None  # re-sent to a Home that reconnects
        self.round_ended_at: datetime | None = None  # when the last round got its result
        self.served_byes: set[str] = set()  # `bye` is handed to the device once, never replayed
        self.last_heard: tuple[int, str] = (-1, "")  # Agora's last user message (`new_speech`)
        self.generation = 0
        self.started_at: datetime | None = None  # set by a Start that succeeded (D-42)
        self._own_nobody()

    def _own_nobody(self) -> None:
        """Who the session is for (D-42): the Pi's two people until a Start names a web user.

        `user_id` is set only for a session started with a user; `hint_count` and
        `learning_event_ids` are what its session record counts.
        """
        self.participants: list[Participant] = list(DEMO_PARTICIPANTS)
        self.focus = Language.EN
        self.user_id: str | None = None
        self.hint_count = 0
        self.learning_event_ids: list[str] = []

    def belong_to(
        self, participants: list[Participant], focus: Language, user_id: str | None
    ) -> None:
        """Set whose session this is, and start counting for its record afresh.

        Example: `store.belong_to(list(DEMO_PARTICIPANTS), Language.EN, None)` for the Pi's.
        """
        self.participants, self.focus, self.user_id = list(participants), focus, user_id
        self.hint_count, self.learning_event_ids = 0, []

    def count_hint(self) -> None:
        """One more `hint.created` was published in this session (for any target)."""
        self.hint_count += 1

    def note_saved(self, events: list[LearningEvent]) -> None:
        """Remember the ids of the session user's words saved now, first order, once each."""
        mine = [e.learning_event_id for e in events if self.user_id and e.user_id == self.user_id]
        self.learning_event_ids = list(dict.fromkeys([*self.learning_event_ids, *mine]))

    def invalidate(self) -> None:
        """Mark everything in flight (a pending start or turn) as out of date.

        Stop and Reset call this synchronously; work that began earlier compares `generation`
        before it changes anything and drops itself when it differs.
        """
        self.generation += 1

    def fresh_commands(self, now: datetime) -> list[DeviceCommand]:
        """What the device may still do: nothing past its lifetime, and `bye` only once.

        Example: a `bye` queued 40 seconds ago is dropped; one just served is not served again.
        """
        alive = [c for c in self.commands if c.at is None or now - c.at <= COMMAND_LIFETIME]
        self.commands = [c for c in alive if c.command_id not in self.served_byes]
        handed_out = list(self.commands)
        self.served_byes |= {c.command_id for c in handed_out if c.kind == "bye"}
        return handed_out

    def queue(self, commands: list[DeviceCommand]) -> None:
        """Hand the device more to do; it reads them from its state. Only the last few are kept."""
        self.commands = [*self.commands, *commands][-QUEUE_LIMIT:]

    def new_speech(self, heard: str, position: int) -> str:
        """The part of `heard` that has not been handled yet; remembers `heard` for next time.

        Agora sends everything said since Mochi last finished speaking as ONE user message: after
        a silent reply, or a reply the person talked over, the next request repeats the earlier
        sentences and appends the new one (seen in live sessions, VERIFIED.md). `position` is the
        index of that message in the request. Example: after "A." at position 1,
        `new_speech("A.  B.", 1)` is "B.".
        """
        earlier_position, earlier = self.last_heard
        self.last_heard = (position, heard)
        if earlier and position == earlier_position and heard.startswith(earlier):
            return heard[len(earlier) :].strip()
        return heard

    def end_game(self) -> None:
        """Back to IDLE and `together` without touching history (used by Stop)."""
        self.activity = idle_activity()
        self.round_secrets = ()
        self.private_prompt = None
        self.round_ended_at = None
        self.mode = SessionMode.TOGETHER

    def session_state(self) -> SessionState:
        """The `session.state.changed` payload."""
        return SessionState(
            status=self.status,
            mode=self.mode,
            focus=self.focus,
            capturing=self.capturing,
            participants=[p.user_id for p in self.participants],
        )

    def context(self, words: dict[str, list[LearningEvent]]) -> SessionContext:
        """What intelligence may look at: last 5 turns and hints, the game, saved words."""
        playing = self.activity if self.activity.state is not GameState.IDLE else None
        return SessionContext(
            session_id=SESSION_ID,
            mode=self.mode,
            focus=self.focus,
            participants=list(self.participants),
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
