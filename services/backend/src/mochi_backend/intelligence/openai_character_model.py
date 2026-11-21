"""CharacterModel over any OpenAI-compatible chat-completions API. Never raises; returns None."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus
from mochi_backend.platform.http_client import HTTP_OK, HttpClient, HttpTransportError, JsonValue
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import Language

CHARACTER_FILE = Path(__file__).parent / "character.md"
MIN_VOLUME = (
    20  # the quietest the device lets itself be set (hardware/pi-bridge [audio].min_volume)
)
WORD_NOTE = (
    "The word or expression they are looking for is: {word} (it means: {meaning}). "
    "Teach exactly this one, and show it."
)
# Only real words from this talk go in here, and only a goodbye may use them (D-38).
GIVEN_NOTE = (
    "If the next sentence is a goodbye, your goodbye names one thing they learned from you today: "
    "{words}. Say it in a few words, as something they learned or used well today; that one word "
    "stays as it is, whatever language you are speaking. If the next sentence is not a goodbye, "
    "ignore this note."
)
# No example words in these notes: the model repeats an example given this close to the sentence.
LANGUAGE_NOTES = {
    Language.EN: (
        "The next sentence is in English, so your reply is in English. Do not put Portuguese "
        "words inside an English sentence. Only if you are teaching a Portuguese word or phrase "
        "right now, give it one short sentence of its own that is entirely in Portuguese; "
        "otherwise use no Portuguese at all."
    ),
    Language.PT_BR: (
        "The next sentence is in Brazilian Portuguese, so your reply is in Brazilian Portuguese. "
        "Do not put English words inside a Portuguese sentence. Only if you are teaching an "
        "English word or phrase right now, give it one short sentence of its own that is "
        "entirely in English; otherwise use no English at all."
    ),
}
# Two people talking to each other: Mochi stays out unless the sentence is clearly for it.
OVERHEARD_NOTE = (
    "Nobody clearly called you with the next sentence. If it is meant for the other person, or "
    "they are only talking about you, or it is a filler or an unfinished start, reply with "
    "exactly [quiet]."
)
# The person woke Mochi to talk to it: what they say next is for Mochi unless it clearly is not.
IN_TALK_NOTE = (
    "Nobody said your name in the next sentence, but this person called you to talk with you, so "
    "it is most likely for you: answer it. Reply with exactly [quiet] only when it is clearly "
    "said to another person, or it is just a filler or an unfinished start."
)


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message


class _ChatReply(BaseModel):
    choices: list[_Choice]


def _voices_line(status: DeviceStatus) -> str:
    if not status.voices:
        return "You do not know anyone's voice yet."
    known = f"Voices you know: {', '.join(status.voices)}. "
    if status.speaker:
        return known + f"The person talking to you right now is {status.speaker}."
    return known + "You do not recognise the voice talking right now."


def system_prompt(status: DeviceStatus, template: str | None = None) -> str:
    """Who Mochi is, what it can do, and what is true right now.

    Example: `system_prompt(DeviceStatus(volume=80))` contains "volume is 80 of 100".
    """
    text = template if template is not None else CHARACTER_FILE.read_text(encoding="utf-8")
    known = {
        "{min_volume}": str(MIN_VOLUME),
        "{volume}": "unknown" if status.volume is None else str(status.volume),
        "{temp}": "unknown" if status.temperature is None else str(status.temperature),
        "{voices}": _voices_line(status),
    }
    for placeholder, value in known.items():
        text = text.replace(placeholder, value)
    return text


def messages_for(request: CharacterRequest, prompt: str) -> list[JsonValue]:
    """The chat: who Mochi is, the recent talk, notes for this sentence, then the sentence."""
    messages: list[JsonValue] = [{"role": "system", "content": prompt}]
    messages += [{"role": e.role, "content": e.text} for e in request.history]
    if request.word:
        note = WORD_NOTE.format(word=request.word, meaning=request.meaning or "unknown")
        messages.append({"role": "system", "content": note})
    if not request.named:
        note = IN_TALK_NOTE if request.woken else OVERHEARD_NOTE
        messages.append({"role": "system", "content": note})
    messages.append({"role": "system", "content": LANGUAGE_NOTES[request.language]})
    if request.given and not request.word:  # last, next to the sentence: it was ignored higher up
        note = GIVEN_NOTE.format(words=", ".join(request.given))
        messages.append({"role": "system", "content": note})
    messages.append({"role": "user", "content": request.text})
    return messages


@dataclass(frozen=True)
class CharacterModelConfig:
    """Which model writes Mochi's lines, and how it is reached."""

    base_url: str
    model_name: str
    api_key: str
    timeout_seconds: float
    # The gpt-5 family thinks before it answers unless told not to: "none" answers at once.
    # Leave empty for a model without that setting (gpt-4.1-mini rejects it).
    reasoning_effort: str = ""


class OpenAiCharacterModel:
    """Example: `OpenAiCharacterModel(http, CharacterModelConfig(url, "gpt-x", key, 6.0))`."""

    def __init__(
        self, http: HttpClient, config: CharacterModelConfig, logger: EventLogger | None = None
    ) -> None:
        self._http = http
        self._config = config
        self._logger = logger
        self._url = f"{config.base_url.rstrip('/')}/chat/completions"
        self._template = CHARACTER_FILE.read_text(encoding="utf-8")

    def _payload(self, request: CharacterRequest) -> JsonValue:
        prompt = system_prompt(request.status, self._template)
        body: dict[str, JsonValue] = {
            "model": self._config.model_name,
            "temperature": 0.7,
            "max_completion_tokens": 256,
            "messages": messages_for(request, prompt),
        }
        if self._config.reasoning_effort:
            body["reasoning_effort"] = self._config.reasoning_effort
        return body

    def _failed(self, why: str) -> None:
        """A reply that fails means Mochi says its fixed line or nothing: say why in the log."""
        if self._logger is not None:
            self._logger.log(
                "character_model_failed", {"model": self._config.model_name, "why": why}
            )

    async def reply(self, request: CharacterRequest) -> str | None:
        """Ask the model; None on transport error, non-200, or a reply without text."""
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        try:
            answer = await self._http.post_json(
                self._url, headers, self._payload(request), self._config.timeout_seconds
            )
            if answer.status != HTTP_OK:
                self._failed(f"HTTP {answer.status}: {answer.body[:200]}")
                return None
            return _ChatReply.model_validate_json(answer.body).choices[0].message.content
        except (HttpTransportError, ValidationError, IndexError) as error:
            self._failed(repr(error)[:200])
            return None
