"""Mochi's side of the conversation: what was said to it lately, and whether it is still in it.

Mochi is quiet by default (AGENTS 1). It answers when someone says its name, and for a short while
after it spoke it also hears the next sentence, so a person can answer its question without saying
"Mochi" again. The model may still decide that sentence was not for it (`[quiet]`).
"""

import asyncio
from datetime import datetime, timedelta

from mochi_backend.intelligence.character_port import (
    CharacterModel,
    CharacterRequest,
    DeviceStatus,
    Exchange,
)
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.platform.clock import Clock
from mochi_contracts import Language

QUIET = "[quiet]"
HISTORY_LIMIT = 8  # lines kept: four things said to Mochi and its four answers
SECONDS_PER_WORD = 0.4  # roughly how long Mochi takes to say a word
FORGET_AFTER = timedelta(minutes=2)  # an old exchange is not context for a new one


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
        self._until: datetime | None = None
        self._woken = False
        self.language = Language.EN  # of the last sentence Mochi answered: the tie-breaker
        self.status = DeviceStatus()

    def use(self, model: CharacterModel) -> None:
        """Swap the model that writes the lines."""
        self._model = model

    def begin(self, woken: bool) -> None:
        """A session starts. `woken`: someone called Mochi on the device to talk to it, so the
        next sentence is for it; otherwise two people talk and Mochi waits for its name."""
        self._history, self._until, self._woken = [], None, woken
        if woken:
            self.called()

    def called(self) -> None:
        """Someone called Mochi without asking anything yet: the next sentence is for it."""
        self._until = self._clock.now() + self._follow_up

    def listening(self) -> bool:
        """True while a sentence that does not say "Mochi" may still be meant for it."""
        return self._until is not None and self._clock.now() < self._until

    def reset(self) -> None:
        """Forget the conversation (demo reset)."""
        self._history, self._until, self._woken = [], None, False

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
        request = CharacterRequest(
            text=text,
            history=self._recent(),
            status=self.status,
            word=word,
            meaning=meaning,
            named=named,
            language=language,
            woken=self._woken,
        )
        try:
            answer = await asyncio.wait_for(self._model.reply(request), self._timeout)
        except TimeoutError:
            return None
        line = spoken_line(answer)
        if line is not None:
            self.language = language
            self._remember(text, line)
        return line

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
