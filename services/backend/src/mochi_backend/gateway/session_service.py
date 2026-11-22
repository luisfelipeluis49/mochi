"""Start and stop the session (and with it the Agora agent): a meeting, or one person's review."""

import asyncio
from dataclasses import dataclass, replace
from datetime import timedelta

from pydantic import BaseModel

from mochi_backend.gateway.after_session import AfterSession
from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStoppedError,
    AgentStartRequest,
    AgoraAgentClient,
    AgoraError,
    AgoraRejectedError,
    RtcTokenIssuer,
    SpeechTuning,
)
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.errors import ConflictError, InvalidRequestError, UpstreamError
from mochi_backend.gateway.roster import SESSION_ID, as_participant
from mochi_backend.gateway.session_history import SessionHistory
from mochi_backend.gateway.user_directory import session_participants
from mochi_backend.storage.session_record import SessionTally, build_record
from mochi_contracts import (
    EventType,
    Language,
    SessionMode,
    SessionState,
    SessionStatus,
    User,
)


class AgoraJoin(BaseModel):
    """Where and how a client joins a session's channel."""

    app_id: str
    channel: str
    uid: int
    token: str


@dataclass(frozen=True)
class SessionConfig:
    """Agora-facing settings for one session (built from `Settings`)."""

    app_id: str
    channel: str
    pi_uid: int
    agent_uid: int
    token_ttl_seconds: int
    llm_url: str
    llm_key: str
    tuning: SpeechTuning
    idle_timeout_seconds: int = 60
    fallback_tuning: SpeechTuning | None = None  # other ears, if Agora refuses the first ones
    greeting_en: str = ""
    greeting_pt: str = ""
    session_id: str = SESSION_ID

    def for_session(self, session_id: str) -> "SessionConfig":
        """This config for another session: its own channel and its own turn endpoint.

        The demo session (the Pi's) keeps the configured channel. Another session joins
        `<channel>-<id>`, so its audio never meets the Pi's, and Agora's cloud calls
        `/agora/llm/<id>/chat/completions`, so its sentences reach its own session.
        Example: `for_session("p-1").channel` is `"mochi-demo-p-1"`.
        """
        if session_id == SESSION_ID:
            return self
        demo_path, own_path = f"/agora/llm/{SESSION_ID}/", f"/agora/llm/{session_id}/"
        return replace(
            self,
            session_id=session_id,
            channel=f"{self.channel}-{session_id}",
            llm_url=self.llm_url.replace(demo_path, own_path, 1),
            tuning=replace(self.tuning, interruption=""),
            fallback_tuning=self._barge_in(self.fallback_tuning),
        )

    @staticmethod
    def _barge_in(tuning: SpeechTuning | None) -> SpeechTuning | None:
        """The same ears with Agora's default interruption: speaking over Mochi cuts it off.

        A web session is one person with headphones, who expects to be able to interrupt (D-57),
        whatever MOCHI_INTERRUPTION says. The Pi's session takes that setting as it is: `append`
        from D-40 until D-67, Agora's default since (render.yaml), so Mochi can be interrupted
        there too.
        """
        return replace(tuning, interruption="") if tuning else None


# First words of a wake phrase that are Portuguese ("oi Mochi", "e aí Mochi", "vamos ...").
PORTUGUESE_CUES = {"vamos", "vamo", "oi", "ola", "olá", "alo", "alô", "e", "ei", "bom", "boa"}


def greeting_for(woken_by: str | None, config: SessionConfig) -> str:
    """The greeting in the language Mochi was called in; "" when nobody called it.

    Example: `greeting_for("oi mochi", config)` is `config.greeting_pt`.
    """
    words = (woken_by or "").lower().split()
    if not words:
        return ""
    return config.greeting_pt if words[0] in PORTUGUESE_CUES else config.greeting_en


def language_of_call(woken_by: str | None) -> Language | None:
    """The language Mochi was called in; None when nobody called it.

    Example: `language_of_call("oi mochi")` is `Language.PT_BR`; `"hey mochi"` is `Language.EN`.
    """
    words = (woken_by or "").lower().split()
    if not words:
        return None
    return Language.PT_BR if words[0] in PORTUGUESE_CUES else Language.EN


# What Mochi says first in a review, in the language the person is at home in.
REVIEW_GREETINGS = {
    Language.EN: "Hi! Shall we go over your words?",
    Language.PT_BR: "Oi! Vamos rever as suas palavras?",
}


@dataclass(frozen=True)
class SessionLeaves:
    """What a session leaves behind when it stops: a web user's record of it (D-56), and what
    is worked out from it afterwards (D-54, D-55). Either may be missing (a test's session)."""

    history: SessionHistory | None = None
    after: AfterSession | None = None


class SessionService:
    """`POST /api/sessions/{id}/start` and `.../stop`."""

    def __init__(
        self,
        core: GatewayCore,
        agora: AgoraAgentClient,
        tokens: RtcTokenIssuer,
        config: SessionConfig,
        leaves: "SessionLeaves | None" = None,
    ) -> None:
        self._store = core.store
        self._ids = core.ids
        leaves = leaves or SessionLeaves()
        self._history = leaves.history  # None: this session never leaves a web record
        self._hub = core.hub
        self._intelligence = core.intelligence
        self._live_hint = core.live_hint
        self._silence = core.silence
        self._commit = core.commit
        self._clock = core.clock
        self._logger = core.logger
        self._journal = core.journal
        self._agora = agora
        self._tokens = tokens
        self._config = config
        self._start_lock = asyncio.Lock()
        self._after = leaves.after  # what is worked out once it has stopped (D-54, D-55)

    async def start(
        self,
        woken_by: str | None = None,
        mode: SessionMode = SessionMode.MEETING,
        user_id: str | None = None,
        user: User | None = None,
    ) -> SessionState:
        """Start the agent and begin capturing. Idempotent; an Agora failure leaves no state.

        `woken_by`: the wake phrase the device heard; Mochi greets in that language and the
        meeting begins. `mode` review: `user` (or the roster's `user_id`) goes over their saved
        words with Mochi; `InvalidRequestError` when that person is not known. `user` without a
        review: the person a web session is for (D-56); its participants become that user and
        `guest`. `ConflictError` for such a user on the device's session, or another user than
        the one a running session is for. Example: `await service.start("let's chat", user=u)`.
        """
        person = self._person(mode, user_id, user)
        greeting, language = self._opening(woken_by, mode, person)
        async with self._start_lock:
            if self._store.capturing:
                return self._already_running(mode, person)
            generation = self._store.generation
            agent_id = await self._start_agent(greeting)
            if generation != self._store.generation:
                self._logger.log("start_superseded", {"agent_id": agent_id})
                await self._stop_agent(agent_id)  # a Stop or Reset arrived while Agora was joining
                return self._store.session_state()
            self._begin(agent_id, mode, person)
            self._logger.log("agent_started", {"agent_id": agent_id, "mode": mode.value})
            self._tell_intelligence(woken_by, mode, person, language)
            return await self._publish_state()

    def _tell_intelligence(
        self,
        woken_by: str | None,
        mode: SessionMode,
        person: User | None,
        language: Language | None,
    ) -> None:
        """How Mochi takes part from here on. A review, and a web user's own session that was
        started by its wake phrase, are conversations with Mochi (D-57). A web user's session
        started without it is a quiet listener that may explain an expression aloud (D-62). The
        device's meeting is neither: Mochi waits for its name (D-43)."""
        reviewing = mode is SessionMode.REVIEW
        own = person is not None and not reviewing
        talking = reviewing or (own and bool(woken_by))
        self._intelligence.session_started(talking, language, explains=own)

    def _person(self, mode: SessionMode, user_id: str | None, user: User | None) -> User | None:
        """Who the session is for: the reviewer, a web session's user, or nobody in particular
        (the device's meeting). Raises before anything is started."""
        if mode is SessionMode.REVIEW:
            return user or self._reviewer(user_id)
        if user is not None and self._config.session_id == SESSION_ID:
            raise ConflictError(f"session {SESSION_ID!r} is the device's; start another id")
        return user

    def _reviewer(self, user_id: str | None) -> User:
        person = self._store.roster.user(user_id or "")
        if person is None:
            known = ", ".join(self._store.roster.user_ids())
            raise InvalidRequestError(
                f"a review needs a known user_id; got {user_id!r}, expected one of: {known}"
            )
        return person

    def _already_running(self, mode: SessionMode, person: User | None) -> SessionState:
        """A Start while the session runs changes nothing; one for another web user is refused."""
        theirs = mode is not SessionMode.REVIEW and person is not None
        if theirs and person is not None and person.user_id != self._store.user_id:
            raise ConflictError(
                f"session {self._config.session_id!r} is running for another user; "
                f"expected user_id {self._store.user_id!r} or none"
            )
        return self._store.session_state()

    def _opening(
        self, woken_by: str | None, mode: SessionMode, person: User | None
    ) -> tuple[str, Language | None]:
        """Mochi's first line and its language. A review greets its person in their own language."""
        if mode is not SessionMode.REVIEW or person is None:
            return greeting_for(woken_by, self._config), language_of_call(woken_by)
        home = (person.comfortable_languages or [Language.EN])[0]
        return REVIEW_GREETINGS[home], home

    async def stop(self) -> SessionState:
        """Stop capturing at once, then the agent. Idempotent; a gone agent is fine."""
        self._store.invalidate()
        self._record()  # now: a turn still in flight is dropped by `invalidate` anyway
        agent_id = self._store.agent_id
        self._end_locally()
        async with self._commit:  # a turn that is mid-publish finishes first, then all is cleared
            await self._live_hint.clear()
            closed = self._journal.end()  # after that turn: what it counted belongs here
            shown = self._journal.words_shown()
            state = await self._publish_state()
        if closed is not None and self._after is not None:
            self._after.begin(closed, shown)  # in the background: Stop never waits for a report
        if agent_id is not None:
            await self._stop_agent(agent_id)  # after local capture is off: the Pi sees false now
        return state

    async def interrupt(self) -> bool:
        """Someone started talking while Mochi was: stop its voice now, and have it just listen.

        The device calls this the moment it hears a person over Mochi (D-50). True when a
        running agent was told to stop; False when no session runs or Agora could not be told
        (Mochi's own state goes quiet either way).
        """
        agent_id = self._store.agent_id
        if agent_id is None or not self._store.capturing:
            return False
        self._intelligence.interrupted()
        self._silence.finished_speaking()
        try:
            await self._agora.interrupt(agent_id)
        except AgoraError as error:
            self._logger.log("agora_interrupt_failed", {"agent_id": agent_id, "error": str(error)})
            return False
        self._logger.log("interrupted", {"agent_id": agent_id})
        return True

    def join_info(self) -> AgoraJoin:
        """Where a phone joins this session's channel (its own, never the Pi's)."""
        if not self._store.capturing:
            raise ConflictError("session is not capturing; start it first")
        return AgoraJoin(
            app_id=self._config.app_id,
            channel=self._config.channel,
            uid=self._config.pi_uid,
            token=self._issue(self._config.pi_uid),
        )

    def _record(self) -> None:
        """Leave the web session record of a session started with a user, once (D-56)."""
        store, started = self._store, self._store.started_at
        if store.user_id is None or started is None or self._history is None:
            return
        tally = SessionTally(store.user_id, started, store.hint_count, store.learning_event_ids)
        record = build_record(
            self._ids.new("rec"), self._config.session_id, tally, self._clock.now()
        )
        store.user_id, store.started_at = None, None  # a second Stop writes nothing
        self._history.add(record)

    def _claim(self, mode: SessionMode, person: User | None) -> None:
        """Whose session this is from now on: everyone the roster knows (the device's
        meeting), the one person of a review, or a web user and `guest`."""
        if person is None:
            self._store.belong_to(None, Language.EN, None)
        elif mode is SessionMode.REVIEW:
            self._store.belong_to([as_participant(person)], person.target_language, None)
        else:
            people = session_participants(person)
            self._store.belong_to(people, person.target_language, person.user_id)
        self._store.started_at = self._clock.now()

    def _begin(self, agent_id: str, mode: SessionMode, person: User | None) -> None:
        self._claim(mode, person)
        expires = self._clock.now() + timedelta(seconds=self._config.token_ttl_seconds)
        self._store.agent_id = agent_id
        self._store.pi_token = self._issue(self._config.pi_uid)
        self._store.pi_token_expires_at = expires
        self._store.status, self._store.capturing = SessionStatus.ACTIVE, True
        reviewer = person.user_id if mode is SessionMode.REVIEW and person else None
        self._store.mode, self._store.reviewer, self._store.commands = mode, reviewer, []
        self._store.speaker = reviewer  # in a review every sentence is that person's
        # The last session's sentences and hints are not this one's: a hint shown five minutes ago
        # must not count as "a hint in the last two turns" now.
        self._store.turns, self._store.hints = [], []
        self._store.last_heard = (-1, "")
        people = [person.user_id for person in self._store.people()]
        self._journal.begin(self._config.session_id, mode, people)

    def _end_locally(self) -> None:
        self._store.agent_id, self._store.pi_token = None, None
        self._store.commands, self._store.last_heard = [], (-1, "")
        self._store.status, self._store.capturing = SessionStatus.ENDED, False
        self._store.back_to_meeting()  # a review does not carry over into the next session
        self._store.belong_to(None, Language.EN, None)  # nor does a web user's session
        self._silence.finished_speaking()  # a speaking window must not outlive the session

    def _issue(self, uid: int) -> str:
        return self._tokens.issue(self._config.channel, uid, self._config.token_ttl_seconds)

    async def _start_agent(self, greeting: str) -> str:
        """Start with the configured ears; if Agora refuses that request, with the fallback ears.

        Only a refusal (4xx) is tried again: after a timeout the first agent may be running.
        """
        fallback = self._config.fallback_tuning
        try:
            return await self._join(greeting, self._config.tuning)
        except AgoraRejectedError as error:
            if fallback is None:
                raise self._start_failed(error) from error
            self._logger.log("ears_fallback", {"to": fallback.asr_vendor, "because": str(error)})
        except AgoraError as error:
            raise self._start_failed(error) from error
        try:
            return await self._join(greeting, fallback)
        except AgoraError as error:
            raise self._start_failed(error) from error

    def _start_failed(self, error: AgoraError) -> UpstreamError:
        self._logger.log("agora_start_failed", {"error": str(error)})
        return UpstreamError(f"could not start the Agora agent: {error}")

    async def _join(self, greeting: str, tuning: SpeechTuning) -> str:
        request = AgentStartRequest(
            channel=self._config.channel,
            agent_uid=self._config.agent_uid,
            remote_uid=self._config.pi_uid,
            token=self._issue(self._config.agent_uid),
            llm_url=self._config.llm_url,
            llm_key=self._config.llm_key,
            tuning=tuning,
            idle_timeout_seconds=self._config.idle_timeout_seconds,
            greeting=greeting,
        )
        return await self._agora.start_agent(request)

    async def _stop_agent(self, agent_id: str) -> None:
        try:
            await self._agora.stop_agent(agent_id)
        except AgentAlreadyStoppedError:
            self._logger.log("agora_already_stopped", {"agent_id": agent_id})
        except AgoraError as error:
            # Stop locally anyway: the Pi must stop sending even if Agora is unreachable.
            self._logger.log("agora_stop_failed", {"agent_id": agent_id, "error": str(error)})

    async def _publish_state(self) -> SessionState:
        state = self._store.session_state()
        await self._hub.publish(EventType.SESSION_STATE_CHANGED, state)
        return state
