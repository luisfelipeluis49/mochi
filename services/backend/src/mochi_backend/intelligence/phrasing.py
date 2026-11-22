"""One-touch assistance: the whole sentence a stuck speaker was reaching for (DECISIONS D-59).

A hint gives the word. This gives the sentence, a moment later, for the times a word is not
enough: "Because we need to... como é que fala... destravar a autenticação" becomes "Because we
need to unblock the authentication process." Nothing is said unless the person asks for it with
a touch; then Mochi says it for them.
"""

import asyncio

from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.phrase_port import PhraseAnswer, PhraseModel, PhraseRequest
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.tokens import normalized, words_of
from mochi_contracts import Hint, Reason, SessionContext, SessionMode, Turn

MIN_WORDS = 4  # fewer, and there is no sentence to finish ("the, um, garfo")
MAX_WORDS = 22  # a sentence Mochi can say in one breath


class Phraser:
    """Example: `await phraser.suggest(turn, context, hint)` -> "We need to unblock it." or None."""

    def __init__(
        self, model: PhraseModel, lexicon: Lexicon, settings: IntelligenceSettings
    ) -> None:
        self._model = model
        self._lexicon = lexicon
        self._enabled = settings.suggest_phrases
        self._timeout = settings.model_timeout_seconds

    def use(self, model: PhraseModel) -> None:
        """Ask this model from now on. Example: `phraser.use(OpenAiPhraseModel(chat))`."""
        self._model = model

    def _request(self, turn: Turn, context: SessionContext, hint: Hint) -> PhraseRequest | None:
        """What to ask, or None: only a meeting's hint for someone who was saying something.
        Someone who asked Mochi gets their answer aloud already."""
        if not self._enabled or context.mode is not SessionMode.MEETING:
            return None
        if hint.reason is Reason.ASKS_MOCHI or len(words_of(turn.text)) < MIN_WORDS:
            return None
        return PhraseRequest(
            text=turn.text,
            recent_texts=[t.text for t in context.recent_turns[-3:]],
            language=hint.target_language,
            word=hint.expression,
            said=hint.meaning,
        )

    async def suggest(self, turn: Turn, context: SessionContext, hint: Hint) -> str | None:
        """The sentence the speaker was trying to say, or None. Never raises: a suggestion that
        fails must cost nothing else."""
        request = self._request(turn, context, hint)
        if request is None:
            return None
        try:
            answer = await asyncio.wait_for(self._model.phrase(request), self._timeout)
        except Exception:  # noqa: BLE001 - no suggestion is always a safe answer
            return None
        return self.accepted(request, answer)

    def accepted(self, request: PhraseRequest, answer: PhraseAnswer | None) -> str | None:
        """The sentence when it can be said for them: a real sentence, in the language they were
        speaking, short enough, and not just what they said already.

        Example: "I need to postpone my meeting tomorrow." for "I need to adiar my meeting
        tomorrow." is accepted; the same sentence back is not.
        """
        if answer is None or answer.decision != "SUGGEST":
            return None
        sentence = " ".join((answer.sentence or "").split())
        said, wanted = normalized(request.text), normalized(sentence)
        if not wanted or wanted == said or not MIN_WORDS - 1 <= len(wanted.split()) <= MAX_WORDS:
            return None
        if spoken_language(sentence, self._lexicon, request.language) is not request.language:
            return None
        return sentence
