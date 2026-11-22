"""The model port for looking over what one person said in a session (D-54)."""

from typing import Protocol

from pydantic import BaseModel

from mochi_contracts import Language


class CoachRequest(BaseModel):
    """One person's sentences, in order; the language they are learning and the one they know."""

    sentences: list[str]
    target_language: Language
    home_language: Language


class Correction(BaseModel):
    """One sentence put right. `index` is its place in the request's `sentences`."""

    index: int
    better: str
    kind: str | None = None
    topic: str | None = None
    explanation: str | None = None


class CoachAnswer(BaseModel):
    """Strict JSON the model must return."""

    corrections: list[Correction] = []
    strengths: list[str] = []
    focus_next: list[str] = []


class CoachModel(Protocol):
    """Reads one person's sentences and says what was wrong in them."""

    async def review(self, request: CoachRequest) -> CoachAnswer | None:
        """Return the corrections, or None (failure, invalid output, no key)."""
        ...


class NullCoachModel:
    """Used when no model key is configured or reports are switched off: no report is written."""

    async def review(self, request: CoachRequest) -> CoachAnswer | None:
        """Always None. Example: `await NullCoachModel().review(req)` is None."""
        return None
