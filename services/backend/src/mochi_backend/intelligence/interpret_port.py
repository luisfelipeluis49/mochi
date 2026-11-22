"""The model port for "speak for me": saying a sentence of the meeting in its other language
(DECISIONS D-64, D-69)."""

from typing import Literal, Protocol

from pydantic import BaseModel

from mochi_contracts import Language


class InterpretRequest(BaseModel):
    """One sentence, the language it seems to be in (a guess from its small words), and the
    other one, which it is to be said in. The model may find the guess wrong."""

    text: str
    recent_texts: list[str]
    source: Language
    target: Language


class Interpretation(BaseModel):
    """Strict JSON the model must return. NOTHING: there is nothing to say for them."""

    decision: Literal["SAY", "NOTHING"]
    sentence: str | None = None
    language: str | None = None  # the language of `sentence`, when the model says ("en", "pt-BR")


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
