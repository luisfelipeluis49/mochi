"""The language-model port used for words outside the lexicon and for subtle cases 5-9."""

from typing import Literal, Protocol

from pydantic import BaseModel

from mochi_contracts import Language, Reason


class Suspect(BaseModel):
    """A word the lexicon's rules think was used with the meaning of its look-alike.

    Example: "I pretend to travel" -> `Suspect(used="pretend", meant="intend",
    look_alike="pretender")`. Only a suspicion: the model confirms it in the sentence or not.
    """

    used: str
    meant: str
    look_alike: str


class ModelRequest(BaseModel):
    """What the model is asked to judge."""

    text: str
    recent_texts: list[str]
    focus: Language
    candidate_reasons: list[Reason]
    asked_about: str | None = None  # what a "how do you say ...?" in the sentence names
    # What `stuck_signs` saw in the sentence ("stops_short", "describes", ...): clues, not verdicts.
    noticed: list[str] = []
    suspect: Suspect | None = None  # a false friend a rule found, for the model to confirm


class CandidateSuggestion(BaseModel):
    """One of the model's extra candidates, for a reason with no single known word."""

    expression: str | None = None
    meaning: str | None = None


class ModelSuggestion(BaseModel):
    """Strict JSON the model must return."""

    decision: Literal["IGNORE", "SHOW_HINT"]
    reason: Reason | None = None
    expression: str | None = None
    meaning: str | None = None
    example: str | None = None
    confidence: float | None = None  # 0-1, how sure the model is that this word was needed
    expression_language: str | None = None  # the language the model says `expression` is in
    meaning_language: str | None = None  # ... and the language of the word they said (`meaning`)
    # Up to two more plausible completions, asked for only when `reason` is trails_off,
    # restarts or talks_around: there the speaker named no word, so more than one may fit
    # (AGENTS 7.1 cases 5-6). `expression` above is always the first candidate.
    candidates: list[CandidateSuggestion] = []


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
