"""One chain for every turn, whether it came from Agora or from `/dev` (AGENTS 9.2).

Order: take the text -> decide -> apply learning events -> publish -> reply -> remember -> log.
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from mochi_backend.gateway.device_commands import DeviceCommand, Written, split_commands
from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.intelligence_port import IntelligencePort, StreamingDecider
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.prompt_echo import without_prompt_echo
from mochi_backend.gateway.secret_screen import leaked_channel
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.gateway.spoken_release import SpokenOutlet
from mochi_backend.gateway.stale_turns import Gone, StaleTurns, Ticket
from mochi_backend.gateway.voice_directory import VoiceDirectory
from mochi_backend.platform.clock import Clock, iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import (
    Decision,
    DecisionKind,
    EventType,
    GameState,
    Hint,
    LearningEvent,
    LearningState,
    SessionContext,
    Speak,
    Turn,
)


@dataclass(frozen=True)
class TurnOutcome:
    """What the caller needs back: the text for Agora to speak ("" = silence) and the decision."""

    reply: str
    decision: Decision
    segment_id: str | None = None  # the turn's id; None when no turn was run
    stale: bool = False  # cancelled because Agora sent a newer request or hung up (D-37)
    spoken: SpokenOutlet | None = None  # the reply streams from here instead (MOCHI_STREAM_REPLY)


def hint_card(hint: Hint) -> str:
    """What the device shows for a hint, as JSON: a word alone tells too little.

    Example: `{"word": "fork", "language": "en", "meaning": "garfo", "example": null}`.
    """
    card = {
        "word": hint.expression,
        "language": hint.target_language.value,
        "meaning": hint.meaning,
        "example": hint.example,
    }
    return json.dumps(card, ensure_ascii=False)


def used_card(event: LearningEvent) -> str:
    """What the device shows when someone goes on to say a word they were given, as JSON.

    Example: `{"word": "fork", "language": "en"}`.
    """
    card = {"word": event.expression, "language": event.target_language.value}
    return json.dumps(card, ensure_ascii=False)


PLAY = "[play]"  # Mochi was asked for a game: a round starts with this turn
RoundStarter = Callable[[], Awaitable[Speak | None]]  # starts a round, returns the host's line


def silent_decision() -> Decision:
    """IGNORE with nothing attached."""
    return Decision(decision=DecisionKind.IGNORE, hint=None, speak=None, learning_events=[])


@dataclass(frozen=True)
class PipelineDeps:
    """Everything the pipeline is built from (injected by the composition root)."""

    store: SessionStore
    hub: EventHub
    live_hint: LiveHint
    intelligence: IntelligencePort
    silence: SilencePolicy
    clock: Clock
    ids: IdGenerator
    logger: EventLogger
    decide_timeout_seconds: float
    commit_lock: asyncio.Lock
    ears_prompt: str = (
        ""  # what speech-to-text was told, if anything: it can echo into a transcript
    )
    ears_words: tuple[str, ...] = ()
    voices: VoiceDirectory | None = None  # forgetting a voice also deletes the stored copy
    cancel_stale_turns: bool = False  # MOCHI_CANCEL_STALE_TURNS (DECISIONS D-37)
    streamer: StreamingDecider | None = None  # set only with MOCHI_STREAM_REPLY (D-37)


class TurnPipeline:
    """Handles one finished sentence. Turns are processed one at a time."""

    def __init__(self, deps: PipelineDeps) -> None:
        self._store = deps.store
        self._hub = deps.hub
        self._live_hint = deps.live_hint
        self._intelligence = deps.intelligence
        self._silence = deps.silence
        self._clock = deps.clock
        self._ids = deps.ids
        self._logger = deps.logger
        self._timeout = deps.decide_timeout_seconds
        self._lock = asyncio.Lock()
        self._commit = deps.commit_lock
        self._voices = deps.voices
        self._ears_prompt, self._ears_words = deps.ears_prompt, deps.ears_words
        self._start_round: RoundStarter | None = None
        self._stale = StaleTurns(deps.cancel_stale_turns)
        self._streamer = deps.streamer
        self._speaking: set[asyncio.Task[None]] = set()  # streamed turns still running

    def play_with(self, start_round: RoundStarter) -> None:
        """Give the pipeline the way to start a round when Mochi writes `[play]`.

        Example: `pipeline.play_with(activity.start_in_turn)`.
        """
        self._start_round = start_round

    def build_context(self) -> SessionContext:
        """The context for intelligence: history plus the saved words of this session's people."""
        people = [participant.user_id for participant in self._store.participants]
        words = {user: self._intelligence.words_for(user) for user in people}
        return self._store.context(words)

    async def handle_turn(self, text: str) -> TurnOutcome:
        """Run one turn through the whole chain and return the reply for Agora."""
        async with self._lock:
            return await self._handle(text.strip())

    async def handle_heard(
        self,
        heard: str,
        position: int,
        arrived: float | None = None,
        gone: Gone | None = None,
        stream: bool = False,
    ) -> TurnOutcome:
        """A turn as Agora sends it: everything said since Mochi last finished speaking.

        `position` is the index of that user message in the request. Only the part not handled
        before is run through the chain. Example: "A." got silence, then Agora sends "A.  B." at
        the same position: only "B." is a new turn. `arrived` is `time.monotonic()` at the request.
        `gone` returns once Agora hung up; with MOCHI_CANCEL_STALE_TURNS that, or a newer request,
        cancels this turn's deciding and it is answered with silence.
        `stream`: Agora asked for a stream; with MOCHI_STREAM_REPLY the outcome returns at once
        and its `spoken` outlet yields the reply as it is written.
        """
        if stream and self._streamer is not None:
            return self._aloud(heard, position, arrived, gone)
        return await self._queued(heard, position, arrived, self._stale.arrive(gone))

    async def _queued(
        self, heard: str, position: int, arrived: float | None, ticket: Ticket
    ) -> TurnOutcome:
        try:
            async with self._lock:
                return await self._heard(heard.strip(), position, arrived, ticket)
        finally:
            self._stale.leave(ticket)

    def _aloud(
        self, heard: str, position: int, arrived: float | None, gone: Gone | None
    ) -> TurnOutcome:
        """Run the turn in a task the pipeline owns, so a caller hanging up never cuts a commit
        in half; the caller reads what to say from the outlet."""
        generation = self._store.generation
        outlet = SpokenOutlet(lambda: self._may_speak(generation))
        ticket = self._stale.arrive(gone, outlet.spoken)
        ticket.outlet = outlet
        task = asyncio.ensure_future(self._speak_through(heard, position, arrived, ticket, outlet))
        self._speaking.add(task)
        task.add_done_callback(self._speaking.discard)
        return TurnOutcome("", silent_decision(), spoken=outlet)

    async def _speak_through(
        self,
        heard: str,
        position: int,
        arrived: float | None,
        ticket: Ticket,
        outlet: SpokenOutlet,
    ) -> None:
        try:
            outcome = await self._queued(heard, position, arrived, ticket)
            outlet.finish(outcome.reply)
        except Exception as error:  # the stream must end whatever happened
            self._logger.log(
                "reply_stream_failed", {"segment_id": outlet.segment_id, "error": repr(error)}
            )
        finally:
            outlet.close()

    def _may_speak(self, generation: int) -> bool:
        """No Stop or Reset since the turn began, and no round whose word must stay secret."""
        store = self._store
        playing = store.activity.state is GameState.ACTIVE_ROUND
        return generation == store.generation and store.capturing and not playing

    async def _heard(
        self, heard: str, position: int, arrived: float | None, ticket: Ticket
    ) -> TurnOutcome:
        if self._stale.is_stale(ticket):  # a newer request came while this one waited
            self._logger.log("turn_dropped_stale", {"why": "superseded", "deciding": False})
            return TurnOutcome("", silent_decision(), stale=True)
        before = self._store.last_heard
        said = self._store.new_speech(heard, position)
        text = without_prompt_echo(said, self._ears_prompt, self._ears_words)
        if text != " ".join(said.split()):
            self._logger.log("ears_prompt_echo", {"heard": said, "kept": text})
        outcome = await self._handle(text, arrived, ticket)
        if outcome.stale:  # never decided: the newer request must cover this speech again
            self._store.last_heard = before
        return outcome

    async def _handle(
        self, text: str, arrived: float | None = None, ticket: Ticket | None = None
    ) -> TurnOutcome:
        if not text or not self._store.capturing:
            self._logger.log("turn_ignored_not_capturing", {"text_len": len(text)})
            return TurnOutcome("", silent_decision())
        turn = Turn(
            segment_id=self._ids.new("seg"), text=text, received_at=iso_z(self._clock.now())
        )
        self._logger.log("turn", {"segment_id": turn.segment_id, "text": text})
        generation = self._store.generation
        decision = await self._decide_unless_stale(turn, ticket)
        if decision is None:
            why = ticket.why if ticket else None
            self._logger.log("turn_dropped_stale", {"segment_id": turn.segment_id, "why": why})
            return TurnOutcome("", silent_decision(), turn.segment_id, stale=True)
        async with self._commit:  # Stop, Reset and round changes wait until this turn is done
            return await self._commit_turn(turn, decision, generation, arrived)

    async def _commit_turn(
        self, turn: Turn, decision: Decision, generation: int, arrived: float | None = None
    ) -> TurnOutcome:
        if arrived is not None:
            self._logger.log(
                "arrived_to_decided",
                {
                    "segment_id": turn.segment_id,
                    "arrived_monotonic": round(arrived, 3),
                    "arrived_to_decided_ms": round((time.monotonic() - arrived) * 1000, 1),
                },
            )
        if self._superseded(decision, generation):
            self._logger.log("turn_dropped_session_changed", {"segment_id": turn.segment_id})
            return TurnOutcome("", silent_decision())
        decision = await self._with_round(self._without_secret(decision))
        await self._publish_results(decision)
        reply = await self._reply(decision)
        self._store.remember(turn, decision.hint)
        return TurnOutcome(reply, decision, turn.segment_id)

    def _without_secret(self, decision: Decision) -> Decision:
        """Silence a decision that would give the live round's secret word away."""
        secrets = self._store.round_secrets
        if not secrets or self._store.activity.state is not GameState.ACTIVE_ROUND:
            return decision
        channel = leaked_channel(decision, secrets)
        if channel is None:
            return decision
        self._logger.log("secret_leak_blocked", {"channel": channel})
        return silent_decision()

    async def _with_round(self, decision: Decision) -> Decision:
        """Mochi wrote `[play]`: start the round now, and let the host's line follow its own.

        Example: "[play] Let's play!" is said as "Let's play! Ben describes. Ana guesses!".
        """
        speak = decision.speak
        if speak is None or PLAY not in speak.text.lower() or self._start_round is None:
            return decision
        host = await self._start_round()
        if host is None:
            return decision
        if leaked_channel(decision, self._store.round_secrets) is not None:
            # Mochi's line was written before the word was drawn, and can hold it by chance (a
            # word it just taught is the likeliest pick): only the host's line is said then.
            self._logger.log("secret_leak_blocked", {"channel": "play"})
            return silent_decision().model_copy(
                update={"decision": DecisionKind.SPEAK, "speak": host}
            )
        both = speak.model_copy(update={"text": f"{speak.text} {host.text}"})
        return decision.model_copy(update={"speak": both})

    def _superseded(self, decision: Decision, generation: int) -> bool:
        """True when Stop/Reset came while deciding, or a round started (wake phrases may speak)."""
        if generation != self._store.generation or not self._store.capturing:
            return True
        playing = self._store.activity.state is GameState.ACTIVE_ROUND
        return playing and decision.decision is not DecisionKind.SPEAK

    async def _decide_unless_stale(self, turn: Turn, ticket: Ticket | None) -> Decision | None:
        """The decision, or None when Agora gave up on this turn while it was being decided."""
        if ticket is None:
            return await self._decide(turn)
        return await self._stale.decide(ticket, self._decide(turn, ticket.outlet))

    def _deciding(self, turn: Turn, outlet: SpokenOutlet | None) -> Awaitable[Decision]:
        """`decide`, or with MOCHI_STREAM_REPLY and no round on, the one that may stream."""
        context = self.build_context()
        playing = self._store.activity.state is GameState.ACTIVE_ROUND
        if outlet is None or self._streamer is None or playing:
            return self._intelligence.decide(turn, context)
        outlet.segment_id = turn.segment_id
        return self._streamer.decide_streaming(turn, context, outlet)

    async def _decide(self, turn: Turn, outlet: SpokenOutlet | None = None) -> Decision:
        started = self._clock.now()
        try:
            decision = await asyncio.wait_for(self._deciding(turn, outlet), self._timeout)
        except TimeoutError:
            self._logger.log("decide_failed", {"segment_id": turn.segment_id, "error": "timeout"})
            return silent_decision()
        except Exception as error:  # one bad turn must not stop the session
            self._logger.log("decide_failed", {"segment_id": turn.segment_id, "error": repr(error)})
            return silent_decision()
        millis = (self._clock.now() - started).total_seconds() * 1000
        self._log_decision(turn, decision, millis)
        return decision

    def _log_decision(self, turn: Turn, decision: Decision, millis: float) -> None:
        hint = decision.hint
        self._logger.log(
            "decision",
            {
                "segment_id": turn.segment_id,
                "decision": decision.decision.value,
                "reason": hint.reason.value if hint else None,
                "hint": hint.expression if hint else None,
                "meaning": hint.meaning if hint else None,
                "latency_ms": round(millis, 1),
            },
        )

    async def _publish_results(self, decision: Decision) -> None:
        await self.save_learning_events(decision.learning_events)
        if decision.hint is not None:
            await self._live_hint.show(decision.hint)
            self._store.count_hint()

    async def save_learning_events(self, proposals: list[LearningEvent]) -> None:
        """`apply()` the proposals, then publish `created` (first state) or `updated`."""
        saved = self._intelligence.apply(proposals)
        self._store.note_saved(saved)  # for the session record (D-42)
        for stored in saved:
            first = len(stored.state_history) == 1
            kind = EventType.LEARNING_EVENT_CREATED if first else EventType.LEARNING_EVENT_UPDATED
            await self._hub.publish(kind, stored)

    async def _reply(self, decision: Decision) -> str:
        """Say the words, and hand the device what was written in brackets (never spoken)."""
        text, written = split_commands(decision.speak.text) if decision.speak else ("", [])
        self._tell_device(decision, written)
        if decision.speak is None or not text:
            return ""
        does = " ".join(f"[{kind} {value}]".replace(" ]", "]") for kind, value in written)
        self._logger.log("reply", {"text": text, "commands": does})
        speak: Speak = decision.speak.model_copy(update={"text": text})
        await self._hub.publish(EventType.AGENT_SPEAK_REQUESTED, speak)
        self._silence.begin_speaking(text)
        return text

    def _used_now(self, decision: Decision) -> list[LearningEvent]:
        """Words someone just said after being given them ("Used with help"): the face cheers.

        Not next to a new hint, whose card would cover the cheer at once, and only for a word
        shown in this session: a card saved an hour ago is no reason to cheer now.
        """
        if decision.hint is not None:
            return []
        shown = {hint.expression for hint in self._store.hints}
        used = (LearningState.ASSISTED,)
        return [
            event
            for event in decision.learning_events
            if event.learning_state in used and event.expression in shown
        ]

    def _forget_voices(self, written: list[Written]) -> None:
        """`[forget Ana]` makes the device forget a voice; the stored voiceprint goes too."""
        if self._voices is None:
            return
        for kind, value in written:
            if kind == "forget" and value.strip():
                self._voices.forget(value.strip())

    def _tell_device(self, decision: Decision, written: list[Written]) -> None:
        self._forget_voices(written)
        wanted = list(written)
        wanted += [("used", used_card(event)) for event in self._used_now(decision)]
        if decision.hint is not None:
            # A hint goes on Mochi's face as a card: the word, its language and what it means.
            # It replaces a bare [show ...] Mochi wrote for the same turn.
            wanted = [(kind, value) for kind, value in wanted if kind != "show"]
            wanted.append(("hint", hint_card(decision.hint)))
        self._store.queue(
            [
                DeviceCommand(
                    command_id=self._ids.new("cmd"), kind=k, value=v, at=self._clock.now()
                )
                for k, v in wanted
            ]
        )
