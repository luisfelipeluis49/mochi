"""Small curated bilingual lexicon: lets the demo work with no model at all."""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from mochi_backend.intelligence.tokens import has_phrase, normalized
from mochi_contracts import Language

ENTRIES_FILE = Path(__file__).parent / "lexicon_entries.json"


class LexiconEntry(BaseModel):
    """One word in both languages, with an example and describing cues."""

    pt: str
    en: str
    example_en: str
    example_pt: str
    describable: bool
    cues: list[str]

    def word(self, language: Language) -> str:
        """The word in `language`. Example: entry(adiar).word(Language.EN) is "postpone"."""
        return self.en if language is Language.EN else self.pt

    def example(self, language: Language) -> str:
        """An example sentence in `language`."""
        return self.example_en if language is Language.EN else self.example_pt


class FalseFriend(BaseModel):
    """A look-alike word used with the wrong meaning, caught by a trigger pattern."""

    used: str
    intended: str
    meaning: str
    example: str
    trigger: str
    # The language being spoken when the slip happens: "en" is an English word a Portuguese
    # speaker misuses ("pretend"), "pt-BR" a Portuguese one an English speaker does ("excitado").
    language: Language = Language.EN


class LexiconFile(BaseModel):
    """Shape of lexicon_entries.json."""

    entries: list[LexiconEntry]
    false_friends: list[FalseFriend]
    deliberate: list[str]


def other_language(language: Language) -> Language:
    """The other MVP language. Example: `other_language(Language.EN)` is PT_BR."""
    return Language.PT_BR if language is Language.EN else Language.EN


class Lexicon:
    """Lookups over the curated entries. Build with `Lexicon.load()`."""

    def __init__(self, content: LexiconFile) -> None:
        self._content = content

    @classmethod
    def load(cls, path: Path = ENTRIES_FILE) -> "Lexicon":
        """Read the JSON file. Example: `Lexicon.load().entries[0].pt` is "adiar"."""
        return cls(LexiconFile.model_validate(json.loads(path.read_text(encoding="utf-8"))))

    @property
    def entries(self) -> list[LexiconEntry]:
        """Every entry."""
        return self._content.entries

    def entries_with_word(self, normalized_text: str, language: Language) -> list[LexiconEntry]:
        """Entries whose `language` word occurs in the text, in lexicon order."""
        return [e for e in self.entries if has_phrase(normalized_text, e.word(language))]

    def entry_for_cues(self, lowered_text: str) -> LexiconEntry | None:
        """First entry one of whose cue phrases appears as whole words (a described word).

        "it's raining" has the cue "raining"; "training" and "the rainbow" do not.
        """
        words = normalized(lowered_text)
        for entry in self.entries:
            if any(has_phrase(words, cue) for cue in entry.cues):
                return entry
        return None

    def entry_for_expression(self, expression: str) -> LexiconEntry | None:
        """The entry whose English or Portuguese word equals `expression`."""
        wanted = normalized(expression)
        for entry in self.entries:
            if wanted in (normalized(entry.en), normalized(entry.pt)):
                return entry
        return None

    def false_friend_in(self, lowered_text: str, language: Language) -> FalseFriend | None:
        """The false friend of `language` whose trigger pattern matches the text, if any.

        Example: `false_friend_in("i pretend to travel", Language.EN).intended` is "intend".
        """
        for friend in self._content.false_friends:
            if friend.language is language and re.search(friend.trigger, lowered_text):
                return friend
        return None

    def is_deliberate(self, normalized_text: str) -> bool:
        """True when the text contains a name, dish or place meant to stay in its language."""
        return any(has_phrase(normalized_text, item) for item in self._content.deliberate)
