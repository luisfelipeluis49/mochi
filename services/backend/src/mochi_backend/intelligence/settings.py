"""Tunable numbers for the intelligence half."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IntelligenceSettings:
    """Example: `IntelligenceSettings(hint_ttl_seconds=8.0, model_timeout_seconds=2.0)`."""

    hint_ttl_seconds: float = 8.0
    model_timeout_seconds: float = 2.0
    character_timeout_seconds: float = 6.0  # how long Mochi's own reply may take to write
    follow_up_seconds: float = 15.0  # after Mochi spoke, how long the next sentence is still for it
    # While two people talk and Mochi only watches, the model looks at every real sentence, not just
    # the ones the rules find suspicious: a word outside the lexicon has no other way to be noticed.
    judge_every_sentence: bool = True
    min_words_to_judge: int = 3  # "Yes." and "Thank you." are not worth a model call
