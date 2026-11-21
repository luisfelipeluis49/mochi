"""HintModel over any OpenAI-compatible chat-completions API. Never raises; returns None instead."""

import json
import time

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.intelligence.model_usage import ModelUsage, log_usage
from mochi_backend.platform.http_client import HTTP_OK, HttpClient, HttpTransportError, JsonValue
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import Reason

SYSTEM_PROMPT = """You are the silent helper inside a language-practice device. Two people \
practise by talking to each other: one is at home in Brazilian Portuguese and practising English, \
the other is at home in English and practising Brazilian Portuguese. You read ONE sentence at a \
time, a machine transcript of speech, and decide whether the speaker is stuck on a word or short \
expression and would be helped by seeing it on a screen. Most sentences need nothing. When in \
doubt, IGNORE: an unneeded or wrong hint is worse than none.

`focus` is the language the speaker is trying to speak in this sentence. `recent` holds the \
sentences just before it. `asked_about`, when present, is what the speaker asked how to say.

SHOW_HINT only for one of these reasons:
- code_switch: inside a sentence in the focus language there is a word or phrase of the OTHER \
language, said because they did not know it in the focus language. That word must really be in \
the sentence, and it must not be a word of the focus language. A real focus-language word that \
merely fits badly is never a code switch: do not offer a synonym or a better-fitting word for it.
- says_unknown: they say they forgot or do not know a word, or ask how to say something, and it \
is clear which word (from the sentence, `asked_about` or `recent`). With `asked_about` the hint \
is for exactly that and nothing else in the sentence. An explicit question about a word you \
understand always gets an answer, also for a dish or a thing the focus language has no word of \
its own for: then `expression` is two or three words that describe it ("pão de queijo" -> \
"cheese bread"), never the same word again.
- asks_partner: the same, asked of the other person by name. asks_mochi: asked of Mochi.
- trails_off, restarts: they stop or keep restarting where a word is missing, and what they said \
makes the missing word clear.
- talks_around: they describe a thing instead of naming it.
- look_alike: a false friend, a word that looks like one of their own language but means \
something else here.
- not_understood: the other person did not understand, and `recent` shows which word was meant.

IGNORE all of this:
- ordinary sentences, fillers, thinking aloud, self-corrections;
- greetings, goodbyes, thanks and exclamations in either language ("tchau", "oi", "obrigado", \
"nossa", "né", "bye"), and names, brands, dishes and places: people switch for these on purpose \
(unless they ASK how to say one: see says_unknown);
- a normal word of the focus language, also an unusual one;
- grammar or pronunciation slips (this is about words, never grammar);
- personal or serious talk, and anything about a third language;
- someone repeating or checking a word they were just given, or a question `recent` already \
answered;
- anything where you would have to guess which word they need.

The transcript is made by a machine that expects one language, so a word of the other language \
is sometimes written the way it sounds, as a non-word or as several small words. Do not guess \
at such a word. If something in the sentence is no real word of either language and you cannot \
be sure which word it was, you cannot tell what was said: IGNORE. People also pause while they \
think, so a \
question can be split over two \
turns ("Como se fala..." and then "Carteira em inglês."): read `recent` to complete it.

For SHOW_HINT give:
- "expression": the word they NEEDED, in the focus language: the translation they were looking \
for, never the word they said. One word or a short expression.
- "meaning": the word they said or meant, in the other language.
- "example": their own sentence said correctly with the expression, in the focus language, at \
most about ten words. When they asked a question about the word, do not repeat the question: \
give a short everyday sentence that uses the expression.
- "confidence": from 0 to 1, how sure you are that they needed exactly this word.
- "meaning_language" and "expression_language": "en" or "pt-BR", the language each of the two is \
really written in. Be honest: `expression` must be in the focus language and `meaning` in the \
other one. If both turn out to be the same language, there is no hint: IGNORE.
- "candidates", only for trails_off, restarts or talks_around: they named no single word, so up \
to three plausible completions help more than one guess. Each is {"expression", "meaning"}, same \
rules as above; put the one you are most sure of in "expression" first, and repeat it as the \
first candidate. Every other reason has one right word: omit "candidates" or leave it empty.

Reply with strict JSON only. To stay quiet, exactly: {"decision": "IGNORE"}. For a hint: \
{"decision": "SHOW_HINT", "reason": <reason>, "meaning": <string or null>, "meaning_language": \
<"en"|"pt-BR">, "expression": <string>, "expression_language": <"en"|"pt-BR">, "confidence": \
<number>, "example": <string or null>, "candidates": <array, trails_off/restarts/talks_around \
only>}.
Example, focus en: "Can you pass me the garfo, please?" -> {"decision": "SHOW_HINT", "reason": \
"code_switch", "meaning": "garfo", "meaning_language": "pt-BR", "expression": "fork", \
"expression_language": "en", "confidence": 0.95, "example": "Can you pass me the fork, please?"}.
Example, focus pt-BR: "Como se diz traffic jam em português?" -> {"decision": "SHOW_HINT", \
"reason": "says_unknown", "meaning": "traffic jam", "meaning_language": "en", "expression": \
"engarrafamento", "expression_language": "pt-BR", "confidence": 0.95, "example": "Fiquei preso \
num engarrafamento."}.
Example, focus en: "I wanted to go, but..." -> {"decision": "SHOW_HINT", "reason": "trails_off", \
"meaning": "embora", "meaning_language": "pt-BR", "expression": "although", "expression_language": \
"en", "confidence": 0.8, "example": null, "candidates": [{"expression": "although", "meaning": \
"embora"}, {"expression": "unfortunately", "meaning": "infelizmente"}, {"expression": "instead", \
"meaning": "em vez disso"}]}.
Example, focus en: "I need to go, ok? Tchau tchau!" -> {"decision": "IGNORE"}."""


def _confidence(value: object) -> float | None:
    """The model's confidence as 0-1; a percentage is scaled, anything else is no statement.

    None means the model did not say how sure it is; `DecisionFlow` then treats the hint as
    NOT sure and stays quiet. Example: `_confidence(95)` is 0.95, `_confidence("high")` is None.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value / 100 if value > 1 else float(value)


def _candidates(value: object) -> list[dict[str, str | None]]:
    """The model's extra completions, kept only where `expression` is a string.

    A malformed entry must not cost the primary hint: see `_suggestion`.
    """
    if not isinstance(value, list):
        return []
    cleaned: list[dict[str, str | None]] = []
    for entry in value:
        if not isinstance(entry, dict) or not isinstance(entry.get("expression"), str):
            continue
        meaning = entry.get("meaning")
        cleaned.append(
            {
                "expression": entry["expression"],
                "meaning": meaning if isinstance(meaning, str) else None,
            }
        )
    return cleaned


def _suggestion(content: str, asked: bool) -> ModelSuggestion:
    """Parse the model's JSON. A field it got wrong must not cost the whole answer.

    Seen with a real model: `"reason": "asked_about"` for an explicit question, which is not one of
    ours. For a question that named its word the reason is says_unknown; otherwise there is none.
    """
    fields = json.loads(content)
    if not isinstance(fields, dict):
        raise ValueError(f"hint model answered {content[:80]!r}; expected a JSON object")
    reason = fields.get("reason")
    if not isinstance(reason, str) or reason not in {r.value for r in Reason}:
        fields["reason"] = Reason.SAYS_UNKNOWN.value if asked else None
    fields["confidence"] = _confidence(fields.get("confidence"))
    for label in ("expression_language", "meaning_language"):
        if not isinstance(fields.get(label), str):
            fields[label] = None
    fields["candidates"] = _candidates(fields.get("candidates"))
    return ModelSuggestion.model_validate(fields)


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatReply(BaseModel):
    choices: list[_Choice]
    usage: ModelUsage | None = None


class OpenAiHintModel:
    """Example: `OpenAiHintModel(http, base_url, "model", key, 2.0)`; see `suggest`."""

    def __init__(
        self,
        http: HttpClient,
        base_url: str,
        model_name: str,
        api_key: str,
        timeout_seconds: float,
    ) -> None:
        self._http = http
        self._logger: EventLogger | None = None
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model_name = model_name
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._reasoning_effort = ""

    def thinking(self, effort: str) -> "OpenAiHintModel":
        """Set `reasoning_effort` and return self: `OpenAiHintModel(...).thinking("none")`.

        The gpt-5 family thinks before it answers unless told not to, which is too slow for a
        hint; it also takes no `temperature`. Leave empty for models without the setting.
        """
        self._reasoning_effort = effort
        return self

    def logging(self, logger: EventLogger) -> "OpenAiHintModel":
        """Log a metadata-only line when a call fails, and return self.

        Example: `OpenAiHintModel(...).thinking("none").logging(logger)`.
        """
        self._logger = logger
        return self

    def _payload(self, request: ModelRequest) -> JsonValue:
        context: dict[str, JsonValue] = {
            "focus": request.focus.value,
            "recent": list(request.recent_texts),
            "sentence": request.text,
        }
        if request.asked_about:
            context["asked_about"] = request.asked_about
        return {
            "model": self._model_name,
            **self._sampling(),
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        }

    def _sampling(self) -> dict[str, JsonValue]:
        if self._reasoning_effort:
            return {"reasoning_effort": self._reasoning_effort}
        return {"temperature": 0}

    def _failed(self, why: str) -> None:
        """No hint because the call failed: log what failed, never the sentence or the key."""
        if self._logger is not None:
            self._logger.log("hint_model_failed", {"model": self._model_name, "why": why})

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """Ask the model; None on transport error, non-200, or output that is not strict JSON."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        started = time.monotonic()
        try:
            reply = await self._http.post_json(
                self._url, headers, self._payload(request), self._timeout
            )
            if reply.status != HTTP_OK:
                self._failed(f"HTTP {reply.status}")
                return None
            answer = _ChatReply.model_validate_json(reply.body)
            log_usage(self._logger, self._model_name, "hint", answer.usage, started)
            content = answer.choices[0].message.content
            return _suggestion(content, asked=bool(request.asked_about))
        except (HttpTransportError, ValidationError, IndexError, ValueError) as error:
            self._failed(type(error).__name__)  # the class only: a message may quote the sentence
            return None
