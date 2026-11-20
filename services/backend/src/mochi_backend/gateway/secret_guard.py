"""Keeps a round's secret word away from the Audience view until the result (AGENTS 6.2).

A second line of defence behind the routing table: only the free-text fields of a payload are
scanned, not keys, ids or enums, so a secret like "state" cannot block ordinary events.
"""

import json
import re
from collections.abc import Iterator

from mochi_backend.platform.http_client import JsonValue
from mochi_contracts import EventPayload

# Only text a person can read can leak a word; ids, enums and keys never do.
FREE_TEXT_KEYS = frozenset(
    {"public_instruction", "revealed_word", "text", "expression", "meaning", "example"}
)


def _free_text(value: JsonValue, key: str = "") -> Iterator[str]:
    if isinstance(value, str):
        if key in FREE_TEXT_KEYS:
            yield value
        return
    if isinstance(value, dict):
        for name, child in value.items():
            yield from _free_text(child, name)
        return
    for item in value if isinstance(value, list) else []:
        yield from _free_text(item, key)


class SecretGuard:
    """The words that must not appear in public text right now."""

    def __init__(self) -> None:
        self._words: set[str] = set()

    def protect(self, word: str) -> None:
        """Start protecting `word`. Example: `guard.protect("Umbrella")`."""
        self._words.add(word.lower())

    def clear(self) -> None:
        """Stop protecting everything (the round is over)."""
        self._words.clear()

    def leaks(self, payload: EventPayload) -> bool:
        """True when a text value in `payload` starts a word with a protected secret.

        The start of a word is enough: "umbrellas" leaks "umbrella"; "estate" does not leak "state".
        """
        if not self._words:
            return False
        parsed: JsonValue = json.loads(payload.model_dump_json())
        texts = [text.lower() for text in _free_text(parsed)]
        return any(self._found_in(word, texts) for word in self._words)

    @staticmethod
    def _found_in(word: str, texts: list[str]) -> bool:
        pattern = re.compile(rf"(?<!\w){re.escape(word)}")
        return any(pattern.search(text) for text in texts)
