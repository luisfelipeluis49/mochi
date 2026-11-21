"""Describe & Guess (AGENTS 7.5): three states, a stock word, then words the learner needed."""

from mochi_backend.intelligence.learning_rules import with_state
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.word_owner import owner_for
from mochi_backend.platform.clock import Clock, iso_z
from mochi_backend.platform.ids import IdGenerator
from mochi_contracts import (
    Activity,
    ActivityCommand,
    ActivityResult,
    GameState,
    Language,
    LearningEvent,
    LearningState,
    PrivatePrompt,
    RoundResult,
    SessionContext,
    Speak,
    SpeakReason,
    WordSource,
)

PEOPLE_PER_SESSION = 2  # exactly two people (AGENTS 1)
STOCK_WORDS_EN = ("umbrella", "suitcase", "corkscrew")
_HOST_LINES = {
    Language.EN: ("{d} describes. {g} guesses!", "{g} got it!", "Skipped. Next time!"),
    Language.PT_BR: ("{d} descreve. {g} adivinha!", "{g} acertou!", "Pulou. Na próxima!"),
}


def _names(context: SessionContext) -> tuple[str, str]:
    """(guesser, describer): first the learner guesses and the partner describes; then they swap.

    Example: after a round where Ben described, the next round is ("ben", "ana") (AGENTS 7.5).
    """
    if len(context.participants) != PEOPLE_PER_SESSION:
        raise ValueError(
            f"need exactly 2 participants to start a round; got {len(context.participants)}"
        )
    first, second = (p.user_id for p in context.participants)
    before = context.activity.describer_user_id if context.activity else None
    guesser = before if before in (first, second) else (owner_for(context) or first)
    return guesser, (second if guesser == first else first)


def _host_says(line: str, context: SessionContext) -> Speak:
    """A line Mochi says as the game's host. Example: `_host_says("Ana got it!", context)`."""
    return Speak(text=line, language=context.focus, reason=SpeakReason.ACTIVITY_HOST)


def _active_activity(prompt: PrivatePrompt, guesser: str, line: str, learned: bool) -> Activity:
    """The public ACTIVE_ROUND state. It never contains the secret word."""
    return Activity(
        activity_id="describe_and_guess",
        round_id=prompt.round_id,
        state=GameState.ACTIVE_ROUND,
        describer_user_id=prompt.describer_user_id,
        guesser_user_id=guesser,
        public_instruction=line,
        result=None,
        revealed_word=None,
        word_source=WordSource.LEARNING_EVENT if learned else WordSource.STOCK,
    )


class RoundEngine:
    """Starts and finishes rounds. Keeps each round's secret word here, never in Activity."""

    def __init__(self, clock: Clock, ids: IdGenerator, lexicon: Lexicon) -> None:
        self._clock = clock
        self._ids = ids
        self._lexicon = lexicon
        self._secrets: dict[str, PrivatePrompt] = {}

    def reset(self) -> None:
        """Forget unfinished rounds."""
        self._secrets.clear()

    def handle(self, command: ActivityCommand, context: SessionContext) -> ActivityResult:
        """Return the new round state. Raises ValueError for an impossible command."""
        if command.type == "start":
            self._refuse_second_round(context)
            return self._start(context)
        return self._finish(command, context)

    def _refuse_second_round(self, context: SessionContext) -> None:
        active = context.activity
        if active is not None and active.state is GameState.ACTIVE_ROUND:
            raise ValueError(
                f"round {active.round_id!r} is still active; "
                f"send result 'skipped' or reset before starting another"
            )

    def _stock_word(self, context: SessionContext) -> str:
        shown = context.activity.revealed_word if context.activity else None
        previous = self._lexicon.entry_for_expression(shown) if shown else None
        english = [w for w in STOCK_WORDS_EN if self._lexicon.entry_for_expression(w)]
        english = english or list(STOCK_WORDS_EN)
        # Look the last word up in either language, so the list cycles whatever the focus is.
        index = 0
        if previous is not None and previous.en in english:
            index = (english.index(previous.en) + 1) % len(english)
        entry = self._lexicon.entry_for_expression(english[index])
        return entry.word(context.focus) if entry else english[index]

    def _learned_word(self, guesser: str, context: SessionContext) -> LearningEvent | None:
        for event in context.learning_events.get(guesser, []):
            entry = self._lexicon.entry_for_expression(event.expression)
            if entry and entry.describable and event.learning_state is not LearningState.REINFORCED:
                return event
        return None

    def _start(self, context: SessionContext) -> ActivityResult:
        guesser, describer = _names(context)
        learned = self._learned_word(guesser, context)
        word = learned.expression if learned else self._stock_word(context)
        prompt = PrivatePrompt(
            round_id=self._ids.new("round"),
            describer_user_id=describer,
            secret_word=word,
            source_learning_event_id=learned.learning_event_id if learned else None,
        )
        self._secrets[prompt.round_id] = prompt
        line = _HOST_LINES[context.focus][0].format(d=describer.title(), g=guesser.title())
        activity = _active_activity(prompt, guesser, line, learned is not None)
        return ActivityResult(
            activity=activity,
            private_prompt=prompt,
            speak=_host_says(line, context),
            learning_events=[],
        )

    def _finish(self, command: ActivityCommand, context: SessionContext) -> ActivityResult:
        current = context.activity
        if (
            current is None
            or current.state is not GameState.ACTIVE_ROUND
            or current.round_id not in self._secrets
        ):
            state = current.state.value if current else "no activity"
            raise ValueError(f"no active round to finish (state {state}); expected ACTIVE_ROUND")
        if command.result is None:
            raise ValueError("result command needs result 'guessed' or 'skipped'; got None")
        prompt = self._secrets.pop(current.round_id)
        ended = self._result_activity(current, prompt, command.result, context)
        return ActivityResult(
            activity=ended,
            private_prompt=None,
            speak=_host_says(ended.public_instruction or "", context),  # "Ana got it!", aloud
            learning_events=self._reinforced(prompt, command.result, context, current),
        )

    def _result_activity(
        self, current: Activity, prompt: PrivatePrompt, result: RoundResult, context: SessionContext
    ) -> Activity:
        lines = _HOST_LINES[context.focus]
        guesser = (current.guesser_user_id or "").title()
        text = lines[1].format(g=guesser, d="") if result is RoundResult.GUESSED else lines[2]
        return current.model_copy(
            update={
                "state": GameState.ROUND_RESULT,
                "result": result,
                "revealed_word": prompt.secret_word,
                "public_instruction": text,
            }
        )

    def _reinforced(
        self, prompt: PrivatePrompt, result: RoundResult, context: SessionContext, current: Activity
    ) -> list[LearningEvent]:
        if result is not RoundResult.GUESSED or prompt.source_learning_event_id is None:
            return []
        owned = context.learning_events.get(current.guesser_user_id or "", [])
        now = iso_z(self._clock.now())
        return [
            with_state(e, LearningState.REINFORCED, now)
            for e in owned
            if e.learning_event_id == prompt.source_learning_event_id
        ]
