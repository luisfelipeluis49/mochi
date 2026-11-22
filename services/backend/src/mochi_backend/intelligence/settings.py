"""Tunable numbers for the intelligence half."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class IntelligenceSettings:
    """Example: `IntelligenceSettings(hint_ttl_seconds=8.0, model_timeout_seconds=2.0)`."""

    hint_ttl_seconds: float = 8.0
    model_timeout_seconds: float = 2.0
    hedge_after_seconds: float = 1.0  # a hint answer usually takes 0.7 s; then ask a second time
    character_timeout_seconds: float = 6.0  # how long Mochi's own reply may take to write
    follow_up_seconds: float = 15.0  # after Mochi spoke, how long the next sentence is still for it
    # While two people talk and Mochi only watches, the model looks at every real sentence, not just
    # the ones the rules find suspicious: a word outside the lexicon has no other way to be noticed.
    judge_every_sentence: bool = True
    min_words_to_judge: int = 3  # "Yes." and "Thank you." are not worth a model call
    hear_window_seconds: float = 120.0  # "can you pronounce it?" means a hint this recent
    hint_min_confidence: float = 0.7  # a hint the model itself doubts is not shown (quiet first)
    # "two_turns": no unasked hint for two turns after one (AGENTS 7.2). "while_shown": only until
    # the earlier hint has left the screen, and never the same word twice in a row (DECISIONS D-29).
    hint_cooldown: Literal["two_turns", "while_shown"] = "two_turns"
    # Idioms and technical terms are explained to the people listening (DECISIONS D-53).
    explain_terms: bool = True
    explain_min_words: int = 5  # a shorter sentence rarely holds an idiom worth a model call
    explain_min_confidence: float = 0.75  # an explanation the model doubts is not shown
    explain_gap_seconds: float = 20.0  # at least this long between two explanations
    # The whole sentence a stuck speaker was reaching for is suggested after their hint (D-59).
    suggest_phrases: bool = True
    # "Mochi, speak for me": a person's sentences are said aloud in the meeting's language (D-64).
    speak_for_me: bool = True
