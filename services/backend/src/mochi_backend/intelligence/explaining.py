"""Explaining what was just said: an idiom or a technical term the listeners may not know (D-53).

Nobody is stuck here. Someone at home in the language said "let's circle back on that", and the
people still learning it are shown what it means, without a sound. It is not a hint: it saves
no word for anyone, and it is worked out after the sentence has been dealt with, so a stuck
speaker never waits for it.
"""

import asyncio
from datetime import datetime, timedelta

from mochi_backend.intelligence.explain_port import ExplainModel, ExplainRequest, Explanation
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.quiet_rules import is_just_thinking, is_serious
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.tokens import has_phrase, normalized, words_of
from mochi_backend.intelligence.wake_phrase import says_mochi
from mochi_backend.platform.clock import Clock
from mochi_contracts import (
    Language,
    MarkKind,
    SessionContext,
    SessionMode,
    TranscriptMark,
    Turn,
)

MAX_EXPRESSION_WORDS = 5  # more than that is a sentence, and a screen cannot explain a sentence
_KINDS = {"idiom": MarkKind.IDIOM, "technical_term": MarkKind.TECHNICAL_TERM}


def someone_listening_learns(
    context: SessionContext, language: Language, speaker: str | None
) -> bool:
    """True when a person other than the speaker is learning `language`: only they can need a
    sentence in it explained.

    Example: Ben says an English sentence and Ana is learning English -> True; Ana says it and
    she is the only one learning English -> False.
    """
    learners = [p.user_id for p in context.participants if p.target_language == language]
    return any(user != speaker for user in learners)


class Explainer:
    """Example: `await explainer.explain(turn, context)` -> a mark for "circle back", or None.

    One per conversation: it remembers what it has explained, so an expression a team uses in
    every other sentence is explained once per session, and it leaves a pause between two
    explanations so a meeting does not turn into a lesson.
    """

    def __init__(
        self, model: ExplainModel, lexicon: Lexicon, clock: Clock, settings: IntelligenceSettings
    ) -> None:
        self._model = model
        self._lexicon = lexicon
        self._clock = clock
        self._enabled = settings.explain_terms
        self._min_words = settings.explain_min_words
        self._min_confidence = settings.explain_min_confidence
        self._timeout = settings.model_timeout_seconds
        self._gap = timedelta(seconds=settings.explain_gap_seconds)
        self._done: set[str] = set()
        self._last: datetime | None = None
        self._session = 0  # counts sessions: an answer for an earlier one is thrown away

    def use(self, model: ExplainModel) -> None:
        """Ask this model from now on. Example: `explainer.use(OpenAiExplainModel(chat))`."""
        self._model = model

    def fresh_session(self) -> None:
        """A session begins: nothing has been explained in it yet."""
        self._done, self._last = set(), None
        self._session += 1

    def _too_soon(self) -> bool:
        """True while the last explanation is less than the pause ago."""
        return self._last is not None and self._clock.now() - self._last < self._gap

    def _quiet(self, turn: Turn) -> bool:
        """The reasons to say nothing whatever the sentence holds (AGENTS 7.2, and one of its
        own: the last explanation was a moment ago).

        A hint still on the screen is not one of them: the explanation is then marked in the
        transcript, and the gateway keeps its card off the device so the hint is not covered.
        """
        text = turn.text
        if is_serious(text) or is_just_thinking(text) or says_mochi(text):
            return True
        return self._too_soon()

    def _request(self, turn: Turn, context: SessionContext) -> ExplainRequest | None:
        """What to ask the model, or None when this sentence is not worth asking about."""
        if not self._enabled or context.mode is not SessionMode.MEETING:
            return None
        if len(words_of(turn.text)) < self._min_words or self._quiet(turn):
            return None
        language = spoken_language(turn.text, self._lexicon, context.focus)
        if not someone_listening_learns(context, language, turn.speaker_user_id):
            return None
        return ExplainRequest(
            text=turn.text,
            recent_texts=[t.text for t in context.recent_turns[-2:]],
            language=language,
            explain_in=other_language(language),
        )

    async def explain(self, turn: Turn, context: SessionContext) -> TranscriptMark | None:
        """The one expression in the sentence worth explaining, or None. Never raises: a failed
        explanation must cost nothing else."""
        request, session = self._request(turn, context), self._session
        if request is None:
            return None
        try:
            answer = await asyncio.wait_for(self._model.explain(request), self._timeout)
        except Exception:  # noqa: BLE001 - quiet is always a safe answer
            return None
        if session != self._session or self._too_soon():
            return None  # the session ended meanwhile, or another sentence's answer came first
        return self.accepted(turn.text, answer)

    def accepted(self, text: str, answer: Explanation | None) -> TranscriptMark | None:
        """The answer as a mark when it can be shown: sure enough, really in the sentence,
        short, and not explained before in this session.

        Example: "circle back" (0.9) in "Let's circle back on that" -> a mark of kind idiom.
        """
        if answer is None or answer.decision != "EXPLAIN" or answer.kind is None:
            return None
        expression, meaning = (answer.expression or "").strip(), (answer.meaning or "").strip()
        if not self._showable(text, expression, meaning, answer.confidence):
            return None
        self._done.add(normalized(expression))
        self._last = self._clock.now()
        plain = (answer.plain or "").strip() or None
        return TranscriptMark(kind=_KINDS[answer.kind], text=expression, gloss=meaning, plain=plain)

    def _showable(self, text: str, expression: str, meaning: str, sure: float | None) -> bool:
        key = normalized(expression)
        if not key or not meaning or key == normalized(meaning) or key in self._done:
            return False
        if sure is None or sure < self._min_confidence:
            return False
        return len(key.split()) <= MAX_EXPRESSION_WORDS and has_phrase(normalized(text), expression)
