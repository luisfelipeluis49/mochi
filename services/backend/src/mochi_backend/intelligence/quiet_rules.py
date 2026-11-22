"""When to stay silent (AGENTS 7.2): small predicates; `quiet_reason` names the first."""

import re
from datetime import timedelta

from mochi_backend.intelligence.clear_cases import asks_for_word
from mochi_backend.intelligence.language_guess import strip_proper_nouns
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.tokens import folded, lowered, normalized
from mochi_backend.platform.clock import parse_iso_z
from mochi_contracts import Hint, SessionContext, Turn

_SERIOUS = re.compile(
    r"\b(?:funeral|passed away|died|death|cancer|divorce|hospital|diagnos\w*|depress\w*|"
    r"grieving|morreu|falecimento|luto|divorcio)\b"  # matched on accent-folded text
)
_ONLY_THINKING = re.compile(
    r"^(?:(?:hmm+|um+|uh+|well|let me think|let's see|one moment|so)[\s,.…]*)+$"
)
# A correction follows something: "I need to, I mean, I want to...". At the start of a turn the same
# words only pick up the previous turn ("I mean garfo. Eu esqueci minha wallet." was silenced).
_SELF_CORRECTION = re.compile(
    r"\w[\w'’]*[\s,.…]+(?:i mean|no, wait|no wait|sorry, i meant|quer dizer|ou melhor)\b"
)


def hints_of_last_turns(context: SessionContext, ttl_seconds: float) -> list[Hint]:
    """The hints shown for one of the last two turns.

    A hint belongs to a turn when it was created after that turn arrived; its creation time is
    `expires_at - ttl`. Example: hint made at t1, turns t1,t2,t3 -> listed at t2 and t3, not t4.
    """
    turns = context.recent_turns[-2:]
    if not turns:
        return []
    window_start = parse_iso_z(turns[0].received_at)
    ttl = timedelta(seconds=ttl_seconds)
    return [h for h in context.recent_hints if parse_iso_z(h.expires_at) - ttl >= window_start]


def cooldown_active(context: SessionContext, ttl_seconds: float) -> bool:
    """True when a hint was shown for one of the last two turns (see `hints_of_last_turns`)."""
    return bool(hints_of_last_turns(context, ttl_seconds))


def hint_on_screen(context: SessionContext, turn: Turn) -> bool:
    """True while a hint shown earlier had not yet expired when `turn` was heard."""
    heard = parse_iso_z(turn.received_at)
    return any(parse_iso_z(h.expires_at) > heard for h in context.recent_hints)


def is_serious(text: str) -> bool:
    """True for personal or serious conversation. Example: "My father died last year." -> True."""
    return _SERIOUS.search(folded(text)) is not None


def is_just_thinking(text: str) -> bool:
    """True for filler-only turns or a self-correction in the same turn."""
    low = lowered(text).strip()
    return _ONLY_THINKING.match(low) is not None or _SELF_CORRECTION.search(low) is not None


def is_deliberate_switch(text: str, context: SessionContext, lexicon: Lexicon) -> bool:
    """A name, dish or place in the other language, with no stuck lexicon word."""
    norm = normalized(strip_proper_nouns(text))
    stuck = lexicon.entries_with_word(norm, other_language(context.focus))
    return lexicon.is_deliberate(normalized(text)) and not stuck


def lasting_quiet_reason(text: str, context: SessionContext, lexicon: Lexicon) -> str | None:
    """Name of the first quiet rule other than the cooldown that applies, else None.

    These hold whatever was shown before: a serious talk, thinking aloud, a name.
    """
    asked = asks_for_word(text)
    checks = (
        ("serious_conversation", is_serious(text)),
        ("thinking_or_self_correction", is_just_thinking(text)),
        # "How do you say feijoada in English?" is a question, not a dish dropped in on purpose
        ("deliberate_switch", is_deliberate_switch(text, context, lexicon) and not asked),
    )
    return next((name for name, applies in checks if applies), None)


def quiet_reason(
    text: str, context: SessionContext, lexicon: Lexicon, ttl_seconds: float
) -> str | None:
    """Name of the first quiet rule that applies, else None (so the flow may continue)."""
    if cooldown_active(context, ttl_seconds):
        return "cooldown"
    return lasting_quiet_reason(text, context, lexicon)
