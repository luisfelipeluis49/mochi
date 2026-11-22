"""The model port for explaining what was just said: an idiom or a technical term (D-53)."""

from typing import Literal, Protocol

from pydantic import BaseModel

from mochi_contracts import Language


class ExplainRequest(BaseModel):
    """One sentence, the language it is in, and the language to explain in."""

    text: str
    recent_texts: list[str]
    language: Language
    explain_in: Language


class Explanation(BaseModel):
    """Strict JSON the model must return. `plain`: the same thing in simple words of `language`."""

    decision: Literal["IGNORE", "EXPLAIN"]
    kind: Literal["idiom", "technical_term"] | None = None
    expression: str | None = None
    meaning: str | None = None
    plain: str | None = None
    confidence: float | None = None


class ExplainModel(Protocol):
    """Finds the one expression in a sentence a learner would not understand, if there is one."""

    async def explain(self, request: ExplainRequest) -> Explanation | None:
        """Return an explanation, or None (failure, invalid output, no key)."""
        ...


class NullExplainModel:
    """Used when no model key is configured or explaining is switched off."""

    async def explain(self, request: ExplainRequest) -> Explanation | None:
        """Always None. Example: `await NullExplainModel().explain(req)` is None."""
        return None
