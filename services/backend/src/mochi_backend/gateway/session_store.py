"""The one session's in-memory state. Saved words and voices live in storage (D-32), not here."""

from datetime import datetime

from mochi_backend.gateway.device_commands import COMMAND_LIFETIME, QUEUE_LIMIT, DeviceCommand
from mochi_backend.gateway.roster import SESSION_ID, Roster
from mochi_contracts import (
    Hint,
    Language,
    LearningEvent,
    Participant,
    SessionContext,
    SessionMode,
    SessionState,
    SessionStatus,
    Turn,
)

HISTORY_LIMIT = 5


class SessionStore:
    """Status, mode, agent id and the last few turns and hints.

    `roster`: the people a meeting may hold. Example: `SessionStore().session_state().mode`
    is `SessionMode.MEETING`.
    """

    def __init__(self, roster: Roster | None = None) -> None:
        self.roster = roster or Roster()
        self.status = SessionStatus.CREATED
        self.mode = SessionMode.MEETING
        self.reviewer: str | None = None  # in a review: whose words are gone over
        self.speaker: str | None = None  # the user whose voice the device hears now, if known
        self.capturing = False
        self.agent_id: str | None = None
        self.pi_token: str | None = None
        self.pi_token_expires_at: datetime | None = None
        self.turns: list[Turn] = []
        self.hints: list[Hint] = []
        self.commands: list[DeviceCommand] = []  # for the device, newest last (this session's)
        self.served_byes: set[str] = set()  # `bye` is handed to the device once, never replayed
        self.last_heard: tuple[int, str] = (-1, "")  # Agora's last user message (`new_speech`)
        self.generation = 0

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

    def back_to_meeting(self) -> None:
        """A review is over: the next session is a meeting unless its Start says otherwise."""
        self.mode, self.reviewer, self.speaker = SessionMode.MEETING, None, None

    def people(self) -> list[Participant]:
        """Who is in the session: everyone the roster knows, or in a review that one person."""
        everyone = self.roster.participants()
        if self.mode is not SessionMode.REVIEW:
            return everyone
        return [person for person in everyone if person.user_id == self.reviewer]

    def focus(self) -> Language:
        """The language practised: English in a meeting, the reviewer's own target in a review."""
        people = self.people()
        if self.mode is SessionMode.REVIEW and people:
            return people[0].target_language
        return Language.EN

    def session_state(self) -> SessionState:
        """The `session.state.changed` payload."""
        return SessionState(
            status=self.status,
            mode=self.mode,
            focus=self.focus(),
            capturing=self.capturing,
            participants=[person.user_id for person in self.people()],
        )

    def context(self, words: dict[str, list[LearningEvent]]) -> SessionContext:
        """What intelligence may look at: last 5 turns and hints, and saved words."""
        return SessionContext(
            session_id=SESSION_ID,
            mode=self.mode,
            focus=self.focus(),
            participants=self.people(),
            recent_turns=self.turns[-HISTORY_LIMIT:],
            recent_hints=self.hints[-HISTORY_LIMIT:],
            learning_events=words,
        )

    def remember(self, turn: Turn, hint: Hint | None) -> None:
        """Append a handled turn (and its hint, if any) to the history."""
        self.turns = [*self.turns, turn][-HISTORY_LIMIT:]
        if hint is not None:
            self.hints = [*self.hints, hint][-HISTORY_LIMIT:]

    def clear_history(self) -> None:
        """Forget turns and hints (keeps capturing and the mode as they are)."""
        self.turns, self.hints = [], []
