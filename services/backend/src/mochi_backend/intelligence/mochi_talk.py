"""Mochi's side of the conversation: what was said to it lately, and whether it is still in it.

Mochi is quiet by default (AGENTS 1). In a meeting it answers when someone says its name, and for
a short while after it spoke it also hears the next sentence, so a person can answer its question
without saying "Mochi" again. The model may still decide that sentence was not for it (`[quiet]`).
In a review it is the person's conversation partner from the first sentence on.
"""

import asyncio
import re
from collections.abc import Awaitable
from datetime import datetime, timedelta

from mochi_backend.intelligence.character_port import (
    CharacterModel,
    CharacterRequest,
    DeviceStatus,
    Exchange,
    ReviewWord,
    StreamingCharacterModel,
)
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.streamed_line import QUIET, streamed_line
from mochi_backend.platform.clock import Clock
from mochi_backend.platform.text_sink import TextSink
from mochi_contracts import Language

LISTEN = "[listen]"  # Mochi was asked to only watch: from now on it helps silently
CHAT = "[chat]"  # Mochi was asked back into the talk
# QUIET ("[quiet]"): the sentence was not for Mochi. It lives in streamed_line, which needs it.
HISTORY_LIMIT = 8  # lines kept: four things said to Mochi and its four answers
SECONDS_PER_WORD = 0.4  # roughly how long Mochi takes to say a word
FORGET_AFTER = timedelta(minutes=2)  # an old exchange is not context for a new one
# A word Mochi put on its screen.
SHOWN = re.compile(r"\[\s*show\b\s*:?\s*([^\]]+?)\s*\]", re.IGNORECASE)
MIN_WORDS_TO_EXPLAIN = 4  # an idiom needs a few words around it
GIVEN_LIMIT = 3  # words remembered for the goodbye: the newest ones


def spoken_line(answer: str | None) -> str | None:
    """The model's answer, or None when it chose silence or said nothing.

    Example: `spoken_line(" [quiet] ")` is None; `spoken_line("[mood happy] Oi!")` is kept.
    """
    line = (answer or "").strip()
    return None if not line or QUIET in line.lower() else line


class MochiTalk:
    """Build once. `reply` writes Mochi's line; `listening` says whether a follow-up is expected."""

    def __init__(self, clock: Clock, model: CharacterModel, settings: IntelligenceSettings) -> None:
        self._clock = clock
        self._model = model
        self._timeout = settings.character_timeout_seconds
        self._follow_up = timedelta(seconds=settings.follow_up_seconds)
        self._history: list[Exchange] = []
        self._given: list[str] = []  # words Mochi handed over in this session, newest last
        self._until: datetime | None = None
        self._attentive = False  # someone is talking WITH Mochi, not next to it
        self.explains = False  # a quiet listener may explain an expression unasked (web sessions)
        self.reviewing = False  # this session is a review (told to Mochi with every sentence)
        self.review: list[ReviewWord] = []  # in a review: the words to bring back
        self.language = Language.EN  # of the last sentence Mochi answered: the tie-breaker
        self.status = DeviceStatus()

    @property
    def character(self) -> CharacterModel:
        """The model that writes the lines now."""
        return self._model

    def use(self, model: CharacterModel) -> None:
        """Swap the model that writes the lines."""
        self._model = model

    def begin(
        self, conversing: bool, language: Language | None = None, explains: bool = False
    ) -> None:
        """A session starts. `conversing`: one person talks WITH Mochi (a review), so every
        sentence is for it; otherwise people talk to each other and Mochi waits for its name.

        `language`: the one it was greeted in. Until Mochi has answered something, that is the
        tie-breaker for a sentence that could be either language, not the last session's.
        """
        self._history, self._until, self._attentive = [], None, conversing
        self._given, self.review = [], []
        self.explains = explains  # a web session's quiet listener may explain unasked (D-62)
        self.language = language or self.language
        if conversing:
            self.called()

    def called(self) -> None:
        """Someone called Mochi without asking anything yet: the next sentence is for it."""
        self._until = self._clock.now() + self._follow_up

    def may_explain(self, text: str) -> bool:
        """A quiet web session may explain what was said, but a short sentence holds no idiom.

        Example: with `explains` on and nobody chatting, "It is raining cats and dogs." is True.
        """
        return self.explains and not self._attentive and len(text.split()) >= MIN_WORDS_TO_EXPLAIN

    @property
    def attentive(self) -> bool:
        """True while Mochi is part of the talk (a review, or asked in); False while it watches."""
        return self._attentive

    def listening(self) -> bool:
        """True while a sentence that does not say "Mochi" may still be meant for it.

        Someone who talks WITH Mochi has its attention (seen live: a minute after its last
        answer, "Are you still there?" got silence), until they tell it to just listen.
        Between people talking to each other, only for a short while after Mochi spoke.
        """
        if self._attentive:
            return True
        return self._until is not None and self._clock.now() < self._until

    def hush(self) -> None:
        """Someone talked over Mochi: it stops, and what they say next is theirs, not an answer
        to it. Between people talking to each other it waits for its name again; someone who is
        talking WITH it (a review) keeps its attention.

        Example: after `hush()` in a meeting, `listening()` is False.
        """
        if not self._attentive:
            self._until = None

    def reset(self) -> None:
        """Forget the conversation (demo reset)."""
        self._history, self._until, self._attentive = [], None, False
        self._given, self.review = [], []

    async def reply(
        self,
        text: str,
        *,
        named: bool,
        language: Language,
        word: str | None = None,
        meaning: str | None = None,
    ) -> str | None:
        """Mochi's line for `text`, or None (no model, too slow, or it chose to stay quiet).

        `language` is the one the sentence is in; the reply is asked for in the same.
        """
        request = self._request(text, named, language, word, meaning)
        return await self._answered(request, None)

    async def chat(
        self, text: str, *, named: bool, language: Language, sink: TextSink
    ) -> str | None:
        """`reply` with no word to teach, passing the line to `sink` while it is written
        (MOCHI_STREAM_REPLY). The whole line is returned and remembered exactly as `reply` does.

        Example: `await talk.chat("Mochi, how are you?", named=True, language=EN, sink=outlet)`.
        """
        return await self._answered(self._request(text, named, language, None, None), sink)

    def _request(
        self, text: str, named: bool, language: Language, word: str | None, meaning: str | None
    ) -> CharacterRequest:
        return CharacterRequest(
            text=text,
            history=self._recent(),
            status=self.status,
            word=word,
            meaning=meaning,
            named=named,
            language=language,
            conversing=self._attentive,
            explains=self.explains and not self._attentive,
            given=list(self._given),
            reviewing=self.reviewing,
            review=list(self.review),
        )

    async def _answered(self, request: CharacterRequest, sink: TextSink | None) -> str | None:
        try:
            answer = await asyncio.wait_for(self._written(request, sink), self._timeout)
        except TimeoutError:
            return None
        line = spoken_line(answer)
        if line is not None:
            self.language = request.language
            self._remember(request.text, line)
            self._note_given(request.word, line)
            self._change_mode(line)
        return line

    def _written(self, request: CharacterRequest, sink: TextSink | None) -> Awaitable[str | None]:
        """The whole answer; streamed into `sink` on the way when there is one and it can be."""
        model = self._model
        if sink is None or not isinstance(model, StreamingCharacterModel):
            return model.reply(request)
        return streamed_line(model, request, sink)

    def _note_given(self, word: str | None, line: str) -> None:
        """Keep the word Mochi just handed over (the one it was told to teach, or one it showed).

        The history holds only the last few lines, so without this a goodbye after a longer
        talk could not say "today you learned postpone" (D-38).
        """
        found = [word] if word else [shown.strip() for shown in SHOWN.findall(line)]
        known = {w.lower() for w in self._given}
        fresh = [w for w in found if w and w.lower() not in known]
        self._given = [*self._given, *fresh][-GIVEN_LIMIT:]

    def _change_mode(self, line: str) -> None:
        """What Mochi wrote can change how it listens from now on.

        `[listen]`: it only watches; it shows hints and speaks when someone says its name.
        `[chat]`: it is part of the talk again.
        """
        written = line.lower()
        if LISTEN in written:
            self._attentive, self._until = False, None  # no "the next sentence is for me" either
        elif CHAT in written:
            self._attentive = True

    def _recent(self) -> list[Exchange]:
        stale = self._until is None or self._clock.now() > self._until + FORGET_AFTER
        if stale:
            self._history = []
        return list(self._history)

    def _remember(self, text: str, line: str) -> None:
        said = [Exchange(role="user", text=text), Exchange(role="assistant", text=line)]
        self._history = [*self._history, *said][-HISTORY_LIMIT:]
        speaking = timedelta(seconds=SECONDS_PER_WORD * len(line.split()))
        self._until = self._clock.now() + speaking + self._follow_up
