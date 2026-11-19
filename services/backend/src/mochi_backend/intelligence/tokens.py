"""Small text helpers shared by the rules: normalising, tokenising, phrase search."""

import re

_LETTERS = re.compile(r"[^\W\d_]+")


def lowered(text: str) -> str:
    """Lowercase with curly apostrophes straightened. Example: `lowered("What’s")` is `"what's"`."""
    return text.lower().replace("’", "'")


def words_of(text: str) -> list[str]:
    """Lowercase letter-only words; hyphens split words.

    Example: `words_of("Guarda-chuva!")` is `["guarda", "chuva"]`.
    """
    return _LETTERS.findall(lowered(text))


def normalized(text: str) -> str:
    """Words joined by single spaces for phrase search. `"Guarda-chuva"` -> `"guarda chuva"`."""
    return " ".join(words_of(text))


def has_phrase(normalized_text: str, phrase: str) -> bool:
    """True when `phrase` appears as whole words in an already-normalised text.

    Example: `has_phrase("i forgot my guarda chuva", "guarda-chuva")` is True.
    """
    return f" {normalized(phrase)} " in f" {normalized_text} "
