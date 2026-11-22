"""CharacterModel over any OpenAI-compatible chat-completions API. Never raises; returns None."""

import time
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.character_port import (
    CharacterRequest,
    CharacterStreamError,
    DeviceStatus,
)
from mochi_backend.intelligence.hedged import first_answer
from mochi_backend.intelligence.model_usage import ModelUsage, log_usage
from mochi_backend.intelligence.openai_character_stream import chunk_of, is_done
from mochi_backend.platform.http_client import (
    HTTP_OK,
    HttpClient,
    HttpLineStreamer,
    HttpTransportError,
    JsonValue,
)
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import Language

CHARACTER_FILE = Path(__file__).parent / "character.md"
HEDGE_CALL = 2  # the second identical request is the hedge
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


# A quiet listener (a web session nobody woke): it speaks unasked only to explain or correct.
EXPLAIN_NOTE = (
    "Nobody called you: you are listening to a conversation. Speak ONLY if the sentence uses an "
    "idiom, a figure of speech or an expression the other person may not understand, or uses an "
    "expression wrongly or unnaturally, and a short explanation or correction would help. Then "
    "explain it in one or two short sentences in the language of the sentence, and add "
    "[phrase: EXPRESSION | MEANING]. For anything else, grammar slips and small mistakes "
    "included, reply with exactly [quiet]."
)


class _Message(BaseModel):
    content: str | None = None


class _Choice(BaseModel):
    message: _Message


class _ChatReply(BaseModel):
    choices: list[_Choice]
    usage: ModelUsage | None = None


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
        note = (
            IN_TALK_NOTE if request.woken else EXPLAIN_NOTE if request.explains else OVERHEARD_NOTE
        )
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
    # MOCHI_CHARACTER_HEDGE_SECONDS: after this long without an answer the same request is sent
    # again and the first answer wins (DECISIONS D-37). 0 is off. A slow call then costs two.
    hedge_after_seconds: float = 0.0


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
        self._lines: HttpLineStreamer | None = None

    def streaming(self, lines: HttpLineStreamer) -> "OpenAiCharacterModel":
        """Let `stream_reply` read the reply as it is written, and return self (D-37).

        Example: `OpenAiCharacterModel(http, config, logger).streaming(http)`.
        """
        self._lines = lines
        return self

    def _payload(self, request: CharacterRequest) -> dict[str, JsonValue]:
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
        """Ask the model; None on transport error, non-200, or a reply without text.

        With `hedge_after_seconds` a slow request gets an identical second one; the first
        answer is kept and the other cancelled. Example: `await model.reply(request)`.
        """
        hedge = self._config.hedge_after_seconds
        if hedge <= 0:
            return await self._reply_once(request)
        asked = 0

        async def _ask() -> str | None:
            nonlocal asked
            asked += 1
            if asked == HEDGE_CALL:
                self._hedged(hedge)
            return await self._reply_once(request)

        return await first_answer(_ask, hedge, self._config.timeout_seconds)

    def _hedged(self, after: float) -> None:
        if self._logger is not None:
            self._logger.log(
                "character_hedge_used", {"model": self._config.model_name, "after_seconds": after}
            )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._config.api_key}"}

    async def stream_reply(self, request: CharacterRequest) -> AsyncGenerator[str]:
        """The reply in pieces as the model writes them (never hedged).

        Without `streaming(...)` the whole reply comes as one piece. Any failure is logged and
        raised as `CharacterStreamError`; the pieces already given stay given.
        Example: `async for piece in model.stream_reply(request): ...`.
        """
        if self._lines is None:
            yield await self._whole(request)
            return
        try:
            async for piece in self._pieces(self._lines, request, time.monotonic()):
                yield piece
        except (HttpTransportError, ValidationError) as error:
            self._failed(repr(error)[:200])
            raise CharacterStreamError(self._config.model_name) from error

    async def _whole(self, request: CharacterRequest) -> str:
        line = await self.reply(request)
        if line is None:
            raise CharacterStreamError(f"{self._config.model_name}: no reply")
        return line

    async def _pieces(
        self, lines: HttpLineStreamer, request: CharacterRequest, started: float
    ) -> AsyncIterator[str]:
        payload = {**self._payload(request), "stream": True}
        payload["stream_options"] = {"include_usage": True}  # the last chunk carries `usage`
        done = False
        timeout = self._config.timeout_seconds
        async for line in lines.post_lines(self._url, self._headers(), payload, timeout):
            done = done or is_done(line)
            chunk = chunk_of(line)
            if chunk is None:
                continue
            log_usage(self._logger, self._config.model_name, "character", chunk.usage, started)
            if chunk.text:
                yield chunk.text
        if not done:
            raise HttpTransportError(f"POST {self._url} stream ended without [DONE]")

    async def _reply_once(self, request: CharacterRequest) -> str | None:
        headers = self._headers()
        started = time.monotonic()
        try:
            answer = await self._http.post_json(
                self._url, headers, self._payload(request), self._config.timeout_seconds
            )
            if answer.status != HTTP_OK:
                self._failed(f"HTTP {answer.status}: {answer.body[:200]}")
                return None
            written = _ChatReply.model_validate_json(answer.body)
            log_usage(self._logger, self._config.model_name, "character", written.usage, started)
            return written.choices[0].message.content
        except (HttpTransportError, ValidationError, IndexError) as error:
            self._failed(repr(error)[:200])
            return None
