"""Wake phrase: "Hi Mochi" / "Oi Mochi", matched loosely because speech-to-text varies."""

import re

# Greetings that always call Mochi, then closings that only do so outside a round.
_GREETING = r"hi|hey(?:\s+there)?|hello|hallo|oie?|ol[áa]|ei|eai|e\s+a[íi]|opa|ok(?:ay)?|yo|oh|ow"
_THANKS = r"thanks|thank\s+you|thx|obrigad[oa]|valeu"
# Speech-to-text writes Moshi, Mochie, Motchi, Moxi, Mo-chi ... Never "mocha" (a drink; AGENTS 7.2).
_LOOSE_NAME = r"(?:m[oô][\s-]?(?:ch|sh|tch|x)(?:ie|i|y|ee|ê)|mouchi|mushi|moji)(?:['’]?s)?"
_SEPARATOR = r"[,\s-]+"


def _phrase(words: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:{words}){_SEPARATOR}{_LOOSE_NAME}\b", re.IGNORECASE)


_WAKE = _phrase(_GREETING)
_WAKE_OR_THANKS = _phrase(f"{_GREETING}|{_THANKS}")
# Its name alone. Speech-to-text often loses the greeting: "Oi Mochi" arrived as "Wait, Mochi."
# Strict on purpose: "Moji" or "mocha" alone is a cat or a drink, not Mochi.
_NAME = re.compile(r"\bm[oô](?:ch|sh|tch|x)(?:ie|i|y)\b", re.IGNORECASE)


def says_mochi(text: str) -> bool:
    """True when the name is in the turn, greeted or not. Example: "Wait, Mochi." -> True."""
    return _NAME.search(text) is not None


def has_wake_phrase(text: str, round_active: bool = False) -> bool:
    """True when the turn addresses Mochi. Example: `has_wake_phrase("Oi Moshi, ...")` is True.

    "Thanks, Mochi" counts only outside a round; during one only the greetings wake it.
    """
    return _WAKE.search(text) is not None or (
        not round_active and _WAKE_OR_THANKS.search(text) is not None
    )


def without_wake_phrase(text: str) -> str:
    """The turn with the wake phrase removed. Example: "Oi Mochi, hello" -> ", hello"."""
    return _WAKE_OR_THANKS.sub("", text, count=1)
