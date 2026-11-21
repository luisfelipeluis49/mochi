"""The language-model port that writes what Mochi says, in character, when it is spoken to."""

from collections.abc import AsyncGenerator
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from mochi_contracts import Language


class Exchange(BaseModel):
    """One line of the recent talk between a person and Mochi."""

    role: Literal["user", "assistant"]
    text: str


class DeviceStatus(BaseModel):
    """What the device last reported about itself (it can talk about these, and change volume)."""

    volume: int | None = None  # speaker level, 0-100
    temperature: int | None = None  # the processor's, degrees Celsius
    voices: list[str] = []  # whose voices the device knows
    speaker: str | None = None  # whose voice it hears right now, when it recognises it


class CharacterRequest(BaseModel):
    """One sentence for Mochi to answer, with everything it may use."""

    text: str
    history: list[Exchange]
    status: DeviceStatus
    word: str | None = None  # the expression the rules found: the reply must teach exactly this
    meaning: str | None = None
    named: bool = True  # False: nobody clearly called Mochi; it may answer [quiet]
    language: Language = Language.EN  # the language the sentence is in: the reply's language
    woken: bool = False  # the person woke Mochi to talk to it (not a talk between two people)
    given: list[str] = []  # words Mochi handed over earlier in this talk: a goodbye may name one


class CharacterModel(Protocol):
    """Writes Mochi's reply. Returns None on any failure or when unconfigured."""

    async def reply(self, request: CharacterRequest) -> str | None:
        """The reply as the model wrote it (silent commands in square brackets included)."""
        ...


class CharacterStreamError(Exception):
    """The streamed reply broke off: what was already said stays said, nothing more follows."""


@runtime_checkable
class StreamingCharacterModel(Protocol):
    """A character model that can also hand over its reply while writing it (D-37)."""

    async def reply(self, request: CharacterRequest) -> str | None:
        """The whole reply, as `CharacterModel.reply`."""
        ...

    def stream_reply(self, request: CharacterRequest) -> AsyncGenerator[str]:
        """The reply in pieces as written; raises `CharacterStreamError` when it breaks off."""
        ...


class NullCharacterModel:
    """Used when no model key is configured: Mochi keeps its short fixed lines."""

    async def reply(self, request: CharacterRequest) -> str | None:
        """Always None. Example: `await NullCharacterModel().reply(req)` is None."""
        return None
