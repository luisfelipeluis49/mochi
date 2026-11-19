"""`decide()` orchestration: wake phrase, quiet rules, clear cases, subtle cases, model."""

import asyncio

from mochi_backend.intelligence.clear_cases import asks_for_word, detect_clear, find_entry
from mochi_backend.intelligence.hint_builder import (
    CaseMatch,
    HintFactory,
    already_saved,
    match_from_entry,
)
from mochi_backend.intelligence.language_guess import has_foreign_word, is_mostly
from mochi_backend.intelligence.learning_rules import assisted_updates
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.model_port import HintModel, ModelRequest
from mochi_backend.intelligence.quiet_rules import quiet_reason
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.subtle_cases import detect_subtle, marker_for
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


class DecisionFlow:
    """Decides what to do with one turn. Build once, call `run` per turn."""

    def __init__(
        self,
        *,
        clock: Clock,
        factory: HintFactory,
        lexicon: Lexicon,
        model: HintModel,
        settings: IntelligenceSettings,
    ) -> None:
        self._clock = clock
        self._factory = factory
        self._lexicon = lexicon
        self._model = model
        self._ttl = settings.hint_ttl_seconds
        self._model_timeout = settings.model_timeout_seconds

    async def run(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide for `turn`; ASSISTED upgrades ride along whatever the decision is."""
        assisted = assisted_updates(turn, context, self._clock)
        decision = await self._decide(turn, context)
        return decision.model_copy(
            update={"learning_events": [*decision.learning_events, *assisted]}
        )

    async def _decide(self, turn: Turn, context: SessionContext) -> Decision:
        if has_wake_phrase(turn.text):  # the wake phrase beats every quiet rule (AGENTS 7.2)
            return await self._answer_mochi(turn, context)
        if quiet_reason(turn.text, context, self._lexicon, self._ttl):
            return ignore()
        match = await self._find_match(turn.text, context)
        return self._show(match, context) if match else ignore()

    async def _find_match(self, text: str, context: SessionContext) -> CaseMatch | None:
        history = [t.text for t in context.recent_turns]
        found = detect_clear(text, context, self._lexicon) or detect_subtle(
            text, history, context, self._lexicon
        )
        if found or not self._worth_asking_model(text, context):
            return found
        return await self._ask_model(text, history, context)

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

    async def _answer_mochi(self, turn: Turn, context: SessionContext) -> Decision:
        rest = without_wake_phrase(turn.text)
        entry = find_entry(rest, context, self._lexicon)
        match = match_from_entry(entry, Reason.ASKS_MOCHI, context) if entry else None
        if match is None:
            match = await self._ask_model(rest, [], context)
        if match is None:
            return ignore()
        shown = self._show(
            CaseMatch(Reason.ASKS_MOCHI, match.expression, match.meaning, match.example), context
        )
        line = _ANSWER_LINES[context.focus].format(w=match.expression)
        speak = Speak(text=line, language=context.focus, reason=SpeakReason.ASKS_MOCHI)
        return shown.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})
