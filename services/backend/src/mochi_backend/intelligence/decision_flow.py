"""`decide()` orchestration: wake phrase, quiet rules, clear cases, subtle cases, model."""

import asyncio
from dataclasses import dataclass

from mochi_backend.intelligence.clear_cases import asks_for_word, detect_clear, mochi_entry
from mochi_backend.intelligence.hint_builder import (
    CaseMatch,
    HintFactory,
    already_saved,
    match_from_entry,
)
from mochi_backend.intelligence.language_guess import has_foreign_word, is_mostly
from mochi_backend.intelligence.learning_rules import assisted_updates
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.mochi_talk import MochiTalk
from mochi_backend.intelligence.model_port import HintModel, ModelRequest
from mochi_backend.intelligence.quiet_rules import quiet_reason
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.spoken_focus import focus_for
from mochi_backend.intelligence.subtle_cases import detect_subtle, marker_for
from mochi_backend.intelligence.tokens import normalized
from mochi_backend.intelligence.wake_phrase import has_wake_phrase, without_wake_phrase
from mochi_backend.platform.clock import Clock
from mochi_contracts import (
    Decision,
    DecisionKind,
    Language,
    Reason,
    SessionContext,
    Speak,
    SpeakReason,
    Turn,
)

_ANSWER_LINES = {Language.EN: "You can say: {w}.", Language.PT_BR: "Você pode dizer: {w}."}


def ignore() -> Decision:
    """The silent decision."""
    return Decision(decision=DecisionKind.IGNORE, hint=None, speak=None, learning_events=[])


def _saying(decision: Decision, line: str, context: SessionContext) -> Decision:
    """The same decision, with Mochi saying `line` aloud."""
    speak = Speak(text=line, language=context.focus, reason=SpeakReason.ASKS_MOCHI)
    return decision.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})


@dataclass(frozen=True)
class Minds:
    """The two things that think: the model that judges a sentence, and Mochi's own talk."""

    hints: HintModel
    talk: MochiTalk


class DecisionFlow:
    """Decides what to do with one turn. Build once, call `run` per turn."""

    def __init__(
        self,
        *,
        clock: Clock,
        factory: HintFactory,
        lexicon: Lexicon,
        minds: Minds,
        settings: IntelligenceSettings,
    ) -> None:
        self._clock = clock
        self._factory = factory
        self._lexicon = lexicon
        self._model = minds.hints
        self._talk = minds.talk
        self._ttl = settings.hint_ttl_seconds
        self._model_timeout = settings.model_timeout_seconds

    async def run(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide for `turn`; ASSISTED upgrades ride along whatever the decision is."""
        assisted = assisted_updates(turn, context, self._clock, self._ttl)
        decision = await self._decide(turn, context)
        return decision.model_copy(
            update={"learning_events": [*decision.learning_events, *assisted]}
        )

    async def _decide(self, turn: Turn, session_context: SessionContext) -> Decision:
        # The focus is the language this sentence is in (AGENTS 7.3 "the language being spoken").
        spoken = focus_for(turn.text, self._lexicon, session_context.focus)
        context = session_context.model_copy(update={"focus": spoken})
        if has_wake_phrase(turn.text):  # the wake phrase beats every quiet rule (AGENTS 7.2)
            return await self._answer_mochi(turn, context)
        quiet = quiet_reason(turn.text, context, self._lexicon, self._ttl)
        match = None if quiet else await self._find_match(turn.text, context)
        shown = self._show(match, context) if match else ignore()
        line = await self._follow_up(turn, context, match)
        return _saying(shown, line, context) if line else shown

    async def _find_match(self, text: str, context: SessionContext) -> CaseMatch | None:
        history = [t.text for t in context.recent_turns]
        found = detect_clear(text, context, self._lexicon) or detect_subtle(
            text, history, context, self._lexicon
        )
        if found is not None and found.reason is Reason.LOOK_ALIKE:
            return await self._confirmed_by_model(found, text, history, context)
        if found or not self._worth_asking_model(text, context):
            return found
        return await self._ask_model(text, history, context)

    async def _confirmed_by_model(
        self, candidate: CaseMatch, text: str, history: list[str], context: SessionContext
    ) -> CaseMatch | None:
        """A false friend is only a candidate: "I'm actually working" is also correct English.

        AGENTS 7.1 has a model judge case 8 in context, and 7.2 says quiet by default, so with no
        model (or a model that disagrees or is slow) the answer is IGNORE.
        """
        answer = await self._ask_model(text, history, context)
        agrees = answer is not None and answer.expression.lower() == candidate.expression.lower()
        return candidate if agrees else None

    def _worth_asking_model(self, text: str, context: SessionContext) -> bool:
        if asks_for_word(text) or marker_for(text) is not None:
            return True
        return has_foreign_word(text, self._lexicon, context.focus) and is_mostly(
            text, self._lexicon, context.focus
        )

    async def _ask_model(
        self, text: str, history: list[str], context: SessionContext
    ) -> CaseMatch | None:
        request = ModelRequest(
            text=text,
            recent_texts=history[-3:],
            focus=context.focus,
            candidate_reasons=list(Reason),
        )
        try:
            suggestion = await asyncio.wait_for(self._model.suggest(request), self._model_timeout)
        except TimeoutError:
            return None  # AGENTS 7.2: a slow model call means IGNORE
        if suggestion is None or suggestion.decision != "SHOW_HINT":
            return None
        if not (suggestion.expression and suggestion.reason):
            return None
        return CaseMatch(
            suggestion.reason, suggestion.expression, suggestion.meaning, suggestion.example
        )

    def _show(self, match: CaseMatch, context: SessionContext) -> Decision:
        hint = self._factory.hint_for(match, context)
        saved = [] if already_saved(hint, context) else [self._factory.event_for(hint)]
        return Decision(
            decision=DecisionKind.SHOW_HINT, hint=hint, speak=None, learning_events=saved
        )

    async def _follow_up(
        self, turn: Turn, context: SessionContext, match: CaseMatch | None
    ) -> str | None:
        """Right after Mochi spoke, the next sentence may answer it without saying "Mochi".

        Returns Mochi's line, or None: it is not in a conversation, or the sentence was not for it.
        A word the rules found is shown either way, and Mochi is told to teach that one.
        """
        if context.activity is not None or not self._talk.listening():
            return None  # during a round only the wake phrase makes Mochi speak
        word, meaning = (match.expression, match.meaning) if match else (None, None)
        return await self._talk.reply(turn.text, named=False, word=word, meaning=meaning)

    async def _word_asked(self, rest: str, context: SessionContext) -> CaseMatch | None:
        entry = mochi_entry(rest, context, self._lexicon)
        match = match_from_entry(entry, Reason.ASKS_MOCHI, context) if entry else None
        if match is None and asks_for_word(rest):
            match = await self._ask_model(rest, [], context)
        return match

    async def _answer_mochi(self, turn: Turn, context: SessionContext) -> Decision:
        rest = without_wake_phrase(turn.text)
        if not normalized(rest):
            self._talk.called()  # just "Oi Mochi": nothing was asked yet, the next sentence is
            return ignore()
        match = await self._word_asked(rest, context)
        if match is None:  # not a word: a chat, or something for Mochi to do (only in character)
            line = await self._talk.reply(turn.text, named=True)
            return _saying(ignore(), line, context) if line else ignore()
        shown = self._show(
            CaseMatch(Reason.ASKS_MOCHI, match.expression, match.meaning, match.example), context
        )
        line = await self._talk.reply(
            turn.text, named=True, word=match.expression, meaning=match.meaning
        )
        text = line or _ANSWER_LINES[context.focus].format(w=match.expression)
        speak = Speak(text=text, language=context.focus, reason=SpeakReason.ASKS_MOCHI)
        return shown.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})
