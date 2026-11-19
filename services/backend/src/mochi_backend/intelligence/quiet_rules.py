"""When to stay silent (AGENTS 7.2): small predicates; `quiet_reason` names the first."""

import re
from datetime import timedelta

from mochi_backend.intelligence.language_guess import strip_proper_nouns
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.tokens import lowered, normalized
from mochi_backend.platform.clock import parse_iso_z
from mochi_contracts import GameState, SessionContext

_SERIOUS = re.compile(
    r"\b(?:funeral|passed away|died|death|cancer|divorce|hospital|diagnos\w*|depress\w*|"
    r"grieving|morreu|falecimento|luto|câncer|divórcio)\b"
)
_ONLY_THINKING = re.compile(
    r"^(?:(?:hmm+|um+|uh+|well|let me think|let's see|one moment|so)[\s,.…]*)+$"
)
_SELF_CORRECTION = re.compile(
    r"\b(?:i mean|no, wait|no wait|sorry, i meant|quer dizer|ou melhor)\b"
)


def round_is_active(context: SessionContext) -> bool:
    """True while a Describe & Guess round is running."""
    return context.activity is not None and context.activity.state is GameState.ACTIVE_ROUND


def cooldown_active(context: SessionContext, ttl_seconds: float) -> bool:
    """True when a hint was shown for one of the last two turns.

    A hint belongs to a turn when it was created after that turn arrived; its creation time is
    `expires_at - ttl`. Example: hint made at t1, turns t1,t2,t3 -> quiet at t2 and t3, free at t4.
    """
    turns = context.recent_turns[-2:]
    if not turns:
        return False
    window_start = parse_iso_z(turns[0].received_at)
    ttl = timedelta(seconds=ttl_seconds)
    return any(parse_iso_z(h.expires_at) - ttl >= window_start for h in context.recent_hints)


def is_serious(text: str) -> bool:
    """True for personal or serious conversation. Example: "My father died last year." -> True."""
    return _SERIOUS.search(lowered(text)) is not None


def is_just_thinking(text: str) -> bool:
    """True for filler-only turns or a self-correction in the same turn."""
    low = lowered(text).strip()
    return _ONLY_THINKING.match(low) is not None or _SELF_CORRECTION.search(low) is not None


def is_deliberate_switch(text: str, context: SessionContext, lexicon: Lexicon) -> bool:
    """A name, dish or place in the other language, with no stuck lexicon word."""
    norm = normalized(strip_proper_nouns(text))
    stuck = lexicon.entries_with_word(norm, other_language(context.focus))
    return lexicon.is_deliberate(normalized(text)) and not stuck


def quiet_reason(
    text: str, context: SessionContext, lexicon: Lexicon, ttl_seconds: float
) -> str | None:
    """Name of the first quiet rule that applies, else None (so the flow may continue)."""
    checks = (
        ("round_active", round_is_active(context)),
        ("cooldown", cooldown_active(context, ttl_seconds)),
        ("serious_conversation", is_serious(text)),
        ("thinking_or_self_correction", is_just_thinking(text)),
        ("deliberate_switch", is_deliberate_switch(text, context, lexicon)),
    )
    return next((name for name, applies in checks if applies), None)
