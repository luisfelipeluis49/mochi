"""CharacterModel over any OpenAI-compatible chat-completions API. Never raises; returns None."""

from pathlib import Path

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.character_port import CharacterRequest, DeviceStatus
from mochi_backend.platform.http_client import HTTP_OK, HttpClient, HttpTransportError, JsonValue

CHARACTER_FILE = Path(__file__).parent / "character.md"
MIN_VOLUME = (
    20  # the quietest the device lets itself be set (hardware/pi-bridge [audio].min_volume)
)
WORD_NOTE = (
    "The word or expression they are looking for is: {word} (it means: {meaning}). "
    "Teach exactly this one, and show it."
)
UNNAMED_NOTE = (
    "This sentence did not say your name. If it is meant for the other person and not for you, "
    "reply with exactly [quiet]."
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
        messages.append({"role": "system", "content": UNNAMED_NOTE})
    messages.append({"role": "user", "content": request.text})
    return messages


class OpenAiCharacterModel:
    """Example: `OpenAiCharacterModel(http, base_url, "gpt-4.1-mini", key, 6.0)`; see `reply`."""

    def __init__(
        self, http: HttpClient, base_url: str, model_name: str, api_key: str, timeout_seconds: float
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model_name = model_name
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._template = CHARACTER_FILE.read_text(encoding="utf-8")

    def _payload(self, request: CharacterRequest) -> JsonValue:
        prompt = system_prompt(request.status, self._template)
        return {
            "model": self._model_name,
            "temperature": 0.7,
            "max_tokens": 256,
            "messages": messages_for(request, prompt),
        }

    async def reply(self, request: CharacterRequest) -> str | None:
        """Ask the model; None on transport error, non-200, or a reply without text."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            answer = await self._http.post_json(
                self._url, headers, self._payload(request), self._timeout
            )
            if answer.status != HTTP_OK:
                return None
            return _ChatReply.model_validate_json(answer.body).choices[0].message.content
        except (HttpTransportError, ValidationError, IndexError):
            return None
