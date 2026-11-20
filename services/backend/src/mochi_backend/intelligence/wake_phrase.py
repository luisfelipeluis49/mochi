"""Wake phrase: "Hi Mochi" / "Oi Mochi", matched loosely because speech-to-text varies."""

import re

# Speech-to-text writes Moshi, Mochie, Motchi, Moxi ... (AGENTS 7.2).
_WAKE = re.compile(
    r"\b(?:hi|hey|hello|oi|ol[áa]|ei)[,\s]+m[oô](?:ch|sh|tch|x)(?:ie|i|y)\b", re.IGNORECASE
)
# Its name alone. Speech-to-text often loses the greeting: "Oi Mochi" arrived as "Wait, Mochi."
_NAME = re.compile(r"\bm[oô](?:ch|sh|tch|x)(?:ie|i|y)\b", re.IGNORECASE)


def says_mochi(text: str) -> bool:
    """True when the name is in the turn, greeted or not. Example: "Wait, Mochi." -> True."""
    return _NAME.search(text) is not None


def has_wake_phrase(text: str) -> bool:
    """True when the turn addresses Mochi. Example: `has_wake_phrase("Oi Moshi, ...")` is True."""
    return _WAKE.search(text) is not None


def without_wake_phrase(text: str) -> str:
    """The turn with the wake phrase removed. Example: "Oi Mochi, hello" -> ", hello"."""
    return _WAKE.sub("", text, count=1)
