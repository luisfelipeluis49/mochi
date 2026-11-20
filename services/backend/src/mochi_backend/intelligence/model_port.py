"""The language-model port used for words outside the lexicon and for subtle cases 5-9."""

from typing import Literal, Protocol

from pydantic import BaseModel

from mochi_contracts import Language, Reason


class ModelRequest(BaseModel):
    """What the model is asked to judge."""

    text: str
    recent_texts: list[str]
    focus: Language
    candidate_reasons: list[Reason]
    asked_about: str | None = None  # what a "how do you say ...?" in the sentence names


class ModelSuggestion(BaseModel):
    """Strict JSON the model must return."""

    decision: Literal["IGNORE", "SHOW_HINT"]
    reason: Reason | None = None
    expression: str | None = None
    meaning: str | None = None
    example: str | None = None


class HintModel(Protocol):
    """Judges one sentence in context. Returns None on any failure or when unconfigured."""

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """Return a suggestion, or None (timeout, invalid output, no key)."""
        ...


class NullHintModel:
    """Used when no model key is configured: the rule-based cases still work."""

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """Always None. Example: `await NullHintModel().suggest(req)` is None."""
        return None
