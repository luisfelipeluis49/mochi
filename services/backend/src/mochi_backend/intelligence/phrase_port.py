"""The model port for "one-touch assistance" (D-59): the sentence a stuck speaker was
reaching for."""

from typing import Literal, Protocol

from pydantic import BaseModel

from mochi_contracts import Language


class PhraseRequest(BaseModel):
    """What they said, what came before, the language they were trying to speak, and the word
    their hint gave them (`word`, with `said` the word they used instead, if any)."""

    text: str
    recent_texts: list[str]
    language: Language
    word: str
    said: str | None = None


class PhraseAnswer(BaseModel):
    """Strict JSON the model must return."""

    decision: Literal["IGNORE", "SUGGEST"]
    sentence: str | None = None


class PhraseModel(Protocol):
    """Writes the one sentence the speaker was trying to say."""

    async def phrase(self, request: PhraseRequest) -> PhraseAnswer | None:
        """Return the sentence, or None (failure, invalid output, no key)."""
        ...


class NullPhraseModel:
    """Used when no model key is configured or suggestions are switched off."""

    async def phrase(self, request: PhraseRequest) -> PhraseAnswer | None:
        """Always None. Example: `await NullPhraseModel().phrase(req)` is None."""
        return None
