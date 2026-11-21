"""Stops a decision from handing the round's secret word to anyone (AGENTS 6.2).

Independent of who speaks or what role they play: any hint or spoken line that contains the word
(or its meaning, the same word in the other language) is silenced while the round is active.
"""

import re
import unicodedata

from mochi_contracts import Decision


def fold(text: str) -> str:
    """Lower-case without accents. Example: `fold("Umbrélla")` is "umbrella"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def leaked_channel(decision: Decision, secrets: tuple[str, ...]) -> str | None:
    """ "hint" or "speak" when that part of `decision` holds a whole-word secret, else None.

    Example: a SPEAK "Yes, umbrella!" with secrets ("umbrella",) is "speak".
    """
    hint, speak = decision.hint, decision.speak
    if hint is not None and _mentions((hint.expression, hint.meaning, hint.example), secrets):
        return "hint"
    if speak is not None and _mentions((speak.text,), secrets):
        return "speak"
    return None


def _mentions(texts: tuple[str | None, ...], secrets: tuple[str, ...]) -> bool:
    folded = [fold(text) for text in texts if text]
    for secret in secrets:
        pattern = re.compile(rf"(?<!\w){re.escape(fold(secret))}(?!\w)")
        if any(pattern.search(text) for text in folded):
            return True
    return False
