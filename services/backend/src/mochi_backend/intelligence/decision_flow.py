"""`decide()` orchestration: wake phrase, quiet rules, clear cases, subtle cases, model."""

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from mochi_backend.intelligence.clear_cases import (
    addressed_partner,
    asked_term,
    asks_for_word,
    detect_clear,
    mochi_entry,
    question_itself,
    unfinished_question,
)
from mochi_backend.intelligence.hedged import first_answer
from mochi_backend.intelligence.hint_builder import (
    CaseMatch,
    HintFactory,
    already_saved,
    match_from_entry,
)
from mochi_backend.intelligence.language_guess import (
    has_foreign_word,
    is_mostly,
    spoken_language,
)
from mochi_backend.intelligence.learning_rules import assisted_updates
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.mochi_talk import MochiTalk
from mochi_backend.intelligence.model_port import HintModel, ModelRequest, ModelSuggestion
from mochi_backend.intelligence.quiet_rules import (
    cooldown_active,
    hint_on_screen,
    quiet_reason,
)
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.spoken_focus import focus_for
from mochi_backend.intelligence.subtle_cases import detect_subtle, marker_for
from mochi_backend.intelligence.tokens import has_phrase, normalized, words_of
from mochi_backend.intelligence.wake_phrase import (
    has_wake_phrase,
    says_mochi,
    without_wake_phrase,
)
from mochi_backend.platform.clock import Clock, parse_iso_z
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

_SAME_THOUGHT = timedelta(seconds=20)  # a question and its second half are no further apart
_ANSWER_LINES = {Language.EN: "You can say: {w}.", Language.PT_BR: "Você pode dizer: {w}."}


def _needed_word(text: str, expression: str, meaning: str | None) -> tuple[str | None, str | None]:
    """A hint must be the word the person NEEDED. A model sometimes returns the word they said.

    Then the two fields are the wrong way round ("garfo" / "fork" for "pass me the garfo"):
    swap them. With nothing to swap in, there is no hint.
    Example: `_needed_word("pass me the garfo", "garfo", "fork")` is `("fork", "garfo")`.
    """
    said = normalized(text)
    if not has_phrase(said, expression):
        return expression, meaning
    if meaning and not has_phrase(said, meaning):
        return meaning, expression
    return None, None


def _with_its_question(turn: Turn, context: SessionContext) -> Turn:
    """People pause while they search for a word, and the pause ends the turn.

    Seen live: "Como se fala..." and then "Carteira em inglês." arrived as two turns, and neither
    means anything alone. A turn that follows an unfinished question within a few seconds is read
    together with it.
    """
    if not context.recent_turns or not unfinished_question(context.recent_turns[-1].text):
        return turn
    before = context.recent_turns[-1]
    gap = parse_iso_z(turn.received_at) - parse_iso_z(before.received_at)
    if gap > _SAME_THOUGHT:
        return turn
    return turn.model_copy(update={"text": f"{before.text} {turn.text}"})


def same_words(one: str, other: str) -> bool:
    """Example: `same_words("Fork", "fork ")` -> True."""
    return normalized(one) == normalized(other)


def _only_the_word(text: str, expression: str, meaning: str | None) -> bool:
    """True when the whole turn is just the word itself and no question about it.

    Someone who says only "Molho para salada?" is trying the word out or checking it, not stuck.
    """
    said = normalized(text)
    words = {normalized(expression), normalized(meaning or "")} - {""}
    return said in words and not asks_for_word(text)


def _only_extends(expression: str, meaning: str | None) -> bool:
    """A "hint" that just adds to the word they said is an invention, not a translation.

    Seen with a real sentence: "pass me the bathroom" got "bathroom key" for "bathroom".
    """
    if not meaning:
        return False
    return has_phrase(normalized(expression), meaning) or has_phrase(
        normalized(meaning), expression
    )


def ignore() -> Decision:
    """The silent decision."""
    return Decision(decision=DecisionKind.IGNORE, hint=None, speak=None, learning_events=[])


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
        self._judge_everything = settings.judge_every_sentence
        self._min_words = settings.min_words_to_judge
        self._min_confidence = settings.hint_min_confidence
        self._cooldown = settings.hint_cooldown
        self._hedge_after = settings.hedge_after_seconds

    async def run(self, turn: Turn, context: SessionContext) -> Decision:
        """Decide for `turn`; ASSISTED upgrades ride along whatever the decision is."""
        assisted = assisted_updates(turn, context, self._clock, self._ttl)
        decision = await self._decide(turn, context)
        return decision.model_copy(
            update={"learning_events": [*decision.learning_events, *assisted]}
        )

    async def _decide(self, heard: Turn, session_context: SessionContext) -> Decision:
        turn = _with_its_question(heard, session_context)
        # The focus is the language this sentence is in (AGENTS 7.3 "the language being spoken").
        spoken = focus_for(turn.text, self._lexicon, session_context.focus)
        context = session_context.model_copy(update={"focus": spoken})
        if has_wake_phrase(turn.text):  # the wake phrase beats every quiet rule (AGENTS 7.2)
            return await self._answer_mochi(turn, context)
        quiet = quiet_reason(turn.text, context, self._lexicon, self._ttl)
        if quiet == "cooldown" and self._cooldown_lifted(turn, context):
            quiet = None
        match, line = await self._match_and_line(turn, context, bool(quiet))
        if match and self._just_shown(match, turn, context):
            match = None
        shown = self._show(match, context) if match else ignore()
        return self._saying(shown, line, turn) if line else shown

    def _cooldown_lifted(self, turn: Turn, context: SessionContext) -> bool:
        """The cooldown is against unasked hints piling up; someone asking outright gets theirs.

        With `hint_cooldown="while_shown"` an unasked hint only waits until the earlier one has
        left the screen: two turns are some twenty seconds of real talk, and a second, different
        stuck word in that time went unanswered.
        """
        if asks_for_word(turn.text):
            return True
        return self._cooldown == "while_shown" and not hint_on_screen(context, turn)

    def _just_shown(self, match: CaseMatch, turn: Turn, context: SessionContext) -> bool:
        """The same word as a hint of the last two turns, and nobody asked: once is enough."""
        if asks_for_word(turn.text) or not cooldown_active(context, self._ttl):
            return False
        return any(same_words(h.expression, match.expression) for h in context.recent_hints)

    async def _match_and_line(
        self, turn: Turn, context: SessionContext, quiet: bool
    ) -> tuple[CaseMatch | None, str | None]:
        """The word the rules find in the sentence, and Mochi's line if it may be for Mochi.

        When finding the word needs the hint model, both models are asked at the same time: a
        person waiting for Mochi's answer should not wait for two calls one after the other.
        """
        if quiet:
            return None, await self._follow_up(turn, context, None)
        found = self._by_rules(turn.text, context)
        if not self._needs_model(found, turn.text, context):
            return found, await self._follow_up(turn, context, found)
        return await asyncio.gather(
            self._by_model(found, turn.text, context), self._follow_up(turn, context, None)
        )

    def _by_rules(self, text: str, context: SessionContext) -> CaseMatch | None:
        history = [t.text for t in context.recent_turns]
        return detect_clear(text, context, self._lexicon) or detect_subtle(
            text, history, context, self._lexicon
        )

    def _needs_model(self, found: CaseMatch | None, text: str, context: SessionContext) -> bool:
        if found is not None:
            return found.reason is Reason.LOOK_ALIKE  # a false friend is only a candidate
        return self._worth_asking_model(text, context)

    async def _by_model(
        self, found: CaseMatch | None, text: str, context: SessionContext
    ) -> CaseMatch | None:
        history = [t.text for t in context.recent_turns]
        if found is not None:
            return await self._confirmed_by_model(found, text, history, context)
        answer = await self._ask_model(text, history, context)
        # A false friend the rules did not spot is the model's least reliable call: with a real
        # model "pass me the bathroom" came back as look_alike "toilet". Quiet first (AGENTS 7.2).
        return None if answer and answer.reason is Reason.LOOK_ALIKE else answer

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
        if self._judge_everything and not self._talk.listening():
            # Two people talk and Mochi only watches: every real sentence gets a look. (While
            # someone talks WITH Mochi it answers itself, and a second model call would slow it.)
            return len(words_of(text)) >= self._min_words
        return has_foreign_word(text, self._lexicon, context.focus) and is_mostly(
            text, self._lexicon, context.focus
        )

    async def _ask_model(
        self, text: str, history: list[str], context: SessionContext
    ) -> CaseMatch | None:
        request = ModelRequest(
            text=question_itself(text),
            recent_texts=history[-3:],
            focus=context.focus,
            candidate_reasons=list(Reason),
            asked_about=asked_term(text),
        )
        # AGENTS 7.2: no answer within the limit means IGNORE. A slow first request is asked again.
        suggestion = await first_answer(
            lambda: self._model.suggest(request), self._hedge_after, self._model_timeout
        )
        match = self._accepted(text, suggestion, context.focus)
        if match and match.reason is Reason.ASKS_PARTNER and not addressed_partner(text, context):
            # nobody was named, so nobody in particular was asked: the label must not vary
            match = CaseMatch(Reason.SAYS_UNKNOWN, match.expression, match.meaning, match.example)
        return match

    def _accepted(
        self, text: str, suggestion: ModelSuggestion | None, focus: Language
    ) -> CaseMatch | None:
        """The model's answer as a hint, or None: no hint, incomplete, unsure or off the rules."""
        if suggestion is None or suggestion.decision != "SHOW_HINT":
            return None
        if not (suggestion.expression and suggestion.reason) or self._doubtful(suggestion, focus):
            return None
        if self._made_up(text, suggestion):
            return None
        if _only_the_word(text, suggestion.expression, suggestion.meaning):
            return None  # "Molho para salada?": trying out a word they were just given
        expression, meaning = _needed_word(text, suggestion.expression, suggestion.meaning)
        if expression is None or _only_extends(expression, meaning):
            return None
        return CaseMatch(suggestion.reason, expression, meaning, suggestion.example)

    def _doubtful(self, suggestion: ModelSuggestion, focus: Language) -> bool:
        """The model is not sure itself, or its word is not in the language being practised.

        Seen with real sentences: "maybe a ranch?" (English) got the hint "fazenda". Quiet first.
        """
        unsure = suggestion.confidence is not None and suggestion.confidence < self._min_confidence
        hint_in, said_in = suggestion.expression_language, suggestion.meaning_language
        wrong_side = hint_in is not None and hint_in != focus.value
        same_side = said_in == focus.value and suggestion.reason is Reason.CODE_SWITCH
        return unsure or wrong_side or same_side  # same_side: a synonym, not a translation

    def _made_up(self, text: str, suggestion: ModelSuggestion) -> bool:
        """A code switch names a word of the other language: it has to be in the sentence.

        Seen with a real model: "pass me the bathroom" got "toilet", for a "banheiro" nobody said.
        """
        if suggestion.reason is not Reason.CODE_SWITCH or not suggestion.meaning:
            return False
        said, hint = normalized(text), suggestion.expression or ""
        return not (has_phrase(said, suggestion.meaning) or has_phrase(said, hint))

    def _show(self, match: CaseMatch, context: SessionContext) -> Decision:
        hint = self._factory.hint_for(match, context)
        saved = [] if already_saved(hint, context) else [self._factory.event_for(hint)]
        return Decision(
            decision=DecisionKind.SHOW_HINT, hint=hint, speak=None, learning_events=saved
        )

    async def _follow_up(
        self, turn: Turn, context: SessionContext, match: CaseMatch | None
    ) -> str | None:
        """A sentence without the wake phrase that may still be for Mochi: right after it spoke
        (an answer to its question), or with its name in it (the greeting is often misheard).

        Returns Mochi's line, or None: neither applies, or Mochi judged it was not meant for it.
        A word the rules found is shown either way, and Mochi is told to teach that one.
        """
        maybe_for_mochi = self._talk.listening() or says_mochi(turn.text)
        if context.activity is not None or not maybe_for_mochi:
            return None  # during a round only the wake phrase makes Mochi speak
        return await self._line(turn, match, named=False)

    def _language_of(self, text: str) -> Language:
        """The language the sentence is in; unclear ones follow the last sentence Mochi answered."""
        return spoken_language(text, self._lexicon, self._talk.language)

    async def _line(self, turn: Turn, match: CaseMatch | None, *, named: bool) -> str | None:
        word, meaning = (match.expression, match.meaning) if match else (None, None)
        return await self._talk.reply(
            turn.text,
            named=named,
            language=self._language_of(turn.text),
            word=word,
            meaning=meaning,
        )

    async def _answer_mochi(self, turn: Turn, context: SessionContext) -> Decision:
        rest = without_wake_phrase(turn.text)
        if not normalized(rest):
            self._talk.called()  # just "Oi Mochi": nothing was asked yet, the next sentence is
        entry = mochi_entry(rest, context, self._lexicon)
        match = match_from_entry(entry, Reason.ASKS_MOCHI, context) if entry else None
        if match is None and asks_for_word(rest):  # a word outside the lexicon: ask both at once
            match, line = await asyncio.gather(
                self._ask_model(rest, [], context), self._line(turn, None, named=True)
            )
        else:
            line = await self._line(turn, match, named=True)
        if match is None:  # not a word: a chat, or something for Mochi to do (only in character)
            return self._saying(ignore(), line, turn) if line else ignore()
        shown = self._show(
            CaseMatch(Reason.ASKS_MOCHI, match.expression, match.meaning, match.example), context
        )
        text = line or _ANSWER_LINES[context.focus].format(w=match.expression)
        speak = Speak(text=text, language=context.focus, reason=SpeakReason.ASKS_MOCHI)
        return shown.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})

    def _saying(self, decision: Decision, line: str, turn: Turn) -> Decision:
        """The same decision, with Mochi saying `line` aloud in the language of the sentence."""
        speak = Speak(
            text=line, language=self._language_of(turn.text), reason=SpeakReason.ASKS_MOCHI
        )
        return decision.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})
