"""The model port for "speak for me": saying one person's sentence in the meeting's language
(DECISIONS D-64)."""

from typing import Literal, Protocol

from pydantic import BaseModel

from mochi_contracts import Language


class InterpretRequest(BaseModel):
    """One sentence, the language it was said in, and the language to say it in."""

    text: str
    recent_texts: list[str]
    source: Language
    target: Language


class Interpretation(BaseModel):
    """Strict JSON the model must return. NOTHING: there is nothing to say for them."""

    decision: Literal["SAY", "NOTHING"]
    sentence: str | None = None


class InterpretModel(Protocol):
    """Says a sentence in another language, as its speaker would."""

    async def interpret(self, request: InterpretRequest) -> Interpretation | None:
        """Return the sentence to say, or None (failure, invalid output, no key)."""
        ...


class NullInterpretModel:
    """Used when no model key is configured or the mode is switched off."""

    async def interpret(self, request: InterpretRequest) -> Interpretation | None:
        """Always None. Example: `await NullInterpretModel().interpret(req)` is None."""
        return None
