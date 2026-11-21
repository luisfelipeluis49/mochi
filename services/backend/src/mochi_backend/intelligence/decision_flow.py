"""`decide()` orchestration: wake phrase, quiet rules, clear cases, subtle cases, model."""

import asyncio
from dataclasses import dataclass, replace
from datetime import timedelta

from mochi_backend.intelligence.aloud import wants_to_hear, word_to_hear
from mochi_backend.intelligence.answer_checks import (
    in_its_language,
    language_named,
    made_up,
    only_extends,
    only_the_word,
    open_ask,
    right_way_round,
    same_words,
)
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
    hints_of_last_turns,
    lasting_quiet_reason,
    round_is_active,
)
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.spoken_focus import focus_for
from mochi_backend.intelligence.subtle_cases import detect_subtle, marker_for
from mochi_backend.intelligence.tokens import (
    normalized,
    words_of,
)
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
        self._hear_window = settings.hear_window_seconds

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
        # The wake phrase beats every quiet rule (AGENTS 7.2); a thank-you does not in a round.
        if has_wake_phrase(turn.text, round_is_active(context)):
            return await self._answer_mochi(turn, context)
        return self._said_aloud(turn, context) or await self._watching(turn, context)

    async def _watching(self, turn: Turn, context: SessionContext) -> Decision:
        """Two people talk and nobody called Mochi: a hint when one is needed, else nothing."""
        # A round, a serious talk, thinking aloud or a name keep Mochi quiet whatever came before.
        quiet = lasting_quiet_reason(turn.text, context, self._lexicon) or self._held_back(
            turn, context
        )
        match, line = await self._match_and_line(turn, context, bool(quiet))
        if match and self._just_shown(match, turn, context):
            match = None
        shown = self._show(match, in_its_language(context, match)) if match else ignore()
        if line:
            return self._saying(shown, line, turn)
        hint = shown.hint
        if hint is None or not self._may_be_heard(turn, context):
            return shown
        return self._reading_out(shown, hint.expression, hint.target_language)

    def _may_be_heard(self, turn: Turn, context: SessionContext) -> bool:
        """Someone asked how a word sounds, and it is for Mochi to answer.

        Not when the partner was asked by name, not during a round (only the wake phrase speaks
        there), and not while Mochi is part of the talk: then it answers in its own words.
        """
        asked = wants_to_hear(turn.text) and not addressed_partner(turn.text, context)
        return asked and context.activity is None and not self._talk.attentive

    def _said_aloud(self, turn: Turn, context: SessionContext) -> Decision | None:
        """ "Can you pronounce it?" about a word just shown: Mochi says it, and shows it again.

        The one time Mochi speaks without its name (DECISIONS D-30): the person asked outright,
        and a word on a screen does not tell how it sounds. None when this is not such a turn.
        """
        if not self._may_be_heard(turn, context):
            return None
        word = word_to_hear(turn, context, self._hear_window)
        if word is None or isinstance(word, str):
            return self._reading_out(ignore(), word, context.focus) if word else None
        match = CaseMatch(word.reason, word.expression, word.meaning, word.example)
        again = self._show(match, context.model_copy(update={"focus": word.target_language}))
        return self._reading_out(again, word.expression, word.target_language)

    def _reading_out(self, decision: Decision, word: str, language: Language) -> Decision:
        """The same decision, with Mochi saying just the word, twice: nothing else to mishear."""
        speak = Speak(text=f"{word}. {word}.", language=language, reason=SpeakReason.ASKS_MOCHI)
        return decision.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})

    def _held_back(self, turn: Turn, context: SessionContext) -> str | None:
        """ "cooldown" while an unasked hint has to wait; someone asking outright never waits.

        The team's rule is two turns (AGENTS 7.2). With `hint_cooldown="while_shown"` a hint
        waits only as long as the earlier one is on the screen: two turns are some twenty
        seconds of real talk, and a second, different stuck word in that time went unanswered.
        """
        if asks_for_word(turn.text):
            return None
        if self._cooldown == "while_shown":
            return "cooldown" if hint_on_screen(context, turn) else None
        return "cooldown" if cooldown_active(context, self._ttl) else None

    def _just_shown(self, match: CaseMatch, turn: Turn, context: SessionContext) -> bool:
        """The same word as a hint of the last two turns, and nobody asked: once is enough."""
        if asks_for_word(turn.text):
            return False
        recent = hints_of_last_turns(context, self._ttl)
        return any(same_words(hint.expression, match.expression) for hint in recent)

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
        return await self._model_before_line(found, turn, context)

    async def _model_before_line(
        self, found: CaseMatch | None, turn: Turn, context: SessionContext
    ) -> tuple[CaseMatch | None, str | None]:
        """Both are asked at once, but a hint never waits for Mochi's line (AGENTS 7.2).

        The line is kept only if it is ready when the hint model answers, or when there is no
        hint and the line is all that is left; its own timeout bounds that wait.
        """
        line = asyncio.ensure_future(self._follow_up(turn, context, None))
        try:
            match = await self._by_model(found, turn.text, context)
            if match is None or line.done():
                return match, await line
            return match, None
        finally:
            line.cancel()

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
        answer = await self._ask_model(text, history, context, by_rule=True)
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
        self, text: str, history: list[str], context: SessionContext, by_rule: bool = False
    ) -> CaseMatch | None:
        sentence = question_itself(text)
        request = ModelRequest(
            text=sentence,
            recent_texts=history[-3:],
            focus=context.focus,
            candidate_reasons=list(Reason),
            asked_about=asked_term(sentence),
        )
        # AGENTS 7.2: no answer within the limit means IGNORE. A slow first request is asked again.
        suggestion = await first_answer(
            lambda: self._model.suggest(request), self._hedge_after, self._model_timeout
        )
        match = self._accepted(text, suggestion, context, by_rule)
        if match and match.reason is Reason.ASKS_PARTNER and not addressed_partner(text, context):
            # nobody was named, so nobody in particular was asked: the label must not vary
            match = replace(match, reason=Reason.SAYS_UNKNOWN)
        return match

    def _accepted(
        self,
        text: str,
        suggestion: ModelSuggestion | None,
        context: SessionContext,
        by_rule: bool,
    ) -> CaseMatch | None:
        """The model's answer as a hint, or None: no hint, incomplete, unsure or off the rules."""
        if suggestion is None or suggestion.decision != "SHOW_HINT":
            return None
        answer = right_way_round(text, suggestion)
        if answer is None or not answer.reason or self._rejected(text, answer, context, by_rule):
            return None
        language = language_named(answer.expression_language) if open_ask(text) else None
        return CaseMatch(
            answer.reason, answer.expression or "", answer.meaning, answer.example, language
        )

    def _rejected(
        self, text: str, answer: ModelSuggestion, context: SessionContext, by_rule: bool
    ) -> bool:
        """The checks that keep a wrong or unwanted hint off the screen (DECISIONS D-29)."""
        word, said = answer.expression or "", answer.meaning
        if self._doubtful(answer, context.focus, open_ask(text), by_rule) or made_up(text, answer):
            return True
        if only_the_word(text, answer, context):
            return True  # "Molho para salada?": trying out a word they were just given
        return not asks_for_word(text) and only_extends(word, said)

    def _doubtful(
        self, answer: ModelSuggestion, focus: Language, open_ask: bool, by_rule: bool
    ) -> bool:
        """The model is not sure itself, or its word is not in the language being practised.

        Seen with real sentences: "maybe a ranch?" (English) got the hint "fazenda". Quiet first.
        A question that names no language ("Como se diz abacaxi?") is asked in one language for
        a word of the other, so there the model's own label decides and is not held against it.
        """
        # No stated confidence is no certainty: quiet first (AGENTS 7.2). Only a word the lexicon
        # rules already found (a false-friend candidate the model is confirming) may go without.
        unsure = (answer.confidence is None and not by_rule) or (
            answer.confidence is not None and answer.confidence < self._min_confidence
        )
        hint_in = language_named(answer.expression_language)
        said_in = language_named(answer.meaning_language)
        wrong_side = not open_ask and hint_in is not None and hint_in is not focus
        same_side = said_in is focus and answer.reason is Reason.CODE_SWITCH
        return unsure or wrong_side or same_side  # same_side: a synonym, not a translation

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
        # the language the model found stays: "como se diz abacaxi?" is asked in Portuguese for
        # an English word, which is the English learner's (AGENTS 7.3)
        asked = replace(match, reason=Reason.ASKS_MOCHI)
        shown = self._show(asked, in_its_language(context, asked))
        text = line or _ANSWER_LINES[context.focus].format(w=match.expression)
        speak = Speak(text=text, language=context.focus, reason=SpeakReason.ASKS_MOCHI)
        return shown.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})

    def _saying(self, decision: Decision, line: str, turn: Turn) -> Decision:
        """The same decision, with Mochi saying `line` aloud in the language of the sentence."""
        speak = Speak(
            text=line, language=self._language_of(turn.text), reason=SpeakReason.ASKS_MOCHI
        )
        return decision.model_copy(update={"decision": DecisionKind.SPEAK, "speak": speak})
