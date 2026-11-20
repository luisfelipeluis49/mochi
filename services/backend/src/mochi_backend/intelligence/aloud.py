"""Someone asks to HEAR a word: the one time Mochi speaks without being called by name.

Seen live: "cortar o cabelo" was on the screen, then "você pode pronunciar para mim?" got
silence. A word on a screen does not tell how it sounds (DECISIONS D-30).
"""

import re
from datetime import timedelta

from mochi_backend.intelligence.tokens import lowered, normalized
from mochi_backend.platform.clock import parse_iso_z
from mochi_contracts import Hint, SessionContext, Turn

# About the sound of a word, or "say it for me". Not "say that again": people say that to each
# other when they did not catch something.
_WANTS_TO_HEAR = re.compile(
    r"\bpronounc\w*|\bpronunciation\b|\bpron[uú]nci\w*|"
    r"\bsay (?:it|that|this|the word) (?:out loud|aloud|for me|for us)\b|"
    r"\blet me hear (?:it|that)\b|\bhow does (?:it|that) sound\b|\bem voz alta\b|"
    r"\b(?:fala|falar|diz|dizer|repete|repetir)\b[^?.!]{0,40}"
    r"\b(?:para|pra) (?:mim|n[oó]s|a gente)\b"
)
# A word the recogniser put in quotes: "Você pode falar 'reunião' para mim?"
_QUOTED = re.compile(r"[\"“]([^\"”]{2,40})[\"”]|(?<!\w)['‘]([^'’]{2,40})['’](?!\w)")


def wants_to_hear(text: str) -> bool:
    """True when the turn asks how a word sounds. Example: "Can you pronounce it?" -> True."""
    return _WANTS_TO_HEAR.search(lowered(text)) is not None


def _quoted(text: str) -> str | None:
    found = _QUOTED.search(text)
    return (found.group(1) or found.group(2)).strip() if found else None


def _last_hint(context: SessionContext, turn: Turn, window: timedelta) -> Hint | None:
    """The newest hint still fresh at `turn`: it left the screen at most `window` ago."""
    heard = parse_iso_z(turn.received_at)
    fresh = [h for h in context.recent_hints if heard - parse_iso_z(h.expires_at) <= window]
    return fresh[-1] if fresh else None


def word_to_hear(turn: Turn, context: SessionContext, window_seconds: float) -> Hint | str | None:
    """What to say aloud for a turn that `wants_to_hear`: a recent hint, a quoted word, or None.

    A quoted word wins unless it is the hint's own word or the word the hint stands for:
    "a pronúncia de 'cut my hair'?" after the hint "cortar o cabelo" wants the Portuguese.
    Example: hint "fork" shown a minute ago, "Can you pronounce it?" -> that hint.
    """
    hint = _last_hint(context, turn, timedelta(seconds=window_seconds))
    named = _quoted(turn.text)
    if named is None or hint is None:
        return named or hint
    of_the_hint = {normalized(hint.expression), normalized(hint.meaning or "")}
    return hint if normalized(named) in of_the_hint else named
