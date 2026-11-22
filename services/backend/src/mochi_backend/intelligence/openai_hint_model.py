"""HintModel over any OpenAI-compatible chat-completions API. Never raises; returns None instead."""

import json
import time

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.intelligence.model_usage import ModelUsage, log_usage
from mochi_backend.intelligence.warm_start import open_connections
from mochi_backend.platform.http_client import (
    HTTP_OK,
    HttpClient,
    HttpGetter,
    HttpTransportError,
    JsonValue,
)
from mochi_backend.platform.json_logging import EventLogger
from mochi_contracts import Reason

SYSTEM_PROMPT = """You are the silent helper inside a device that sits in work meetings. Several \
people talk to each other, in English or in Brazilian Portuguese: some of them are at home in \
Brazilian Portuguese and still learning English, others are at home in English and still \
learning Brazilian Portuguese. You do not know who is speaking. You read ONE sentence at a \
time, a machine transcript of speech, and decide whether the speaker is stuck on a word or short \
expression and would be helped by seeing it on a screen. Most sentences need nothing, and an \
unneeded or wrong hint is worse than none. But most people who are stuck never ask: they stop, \
start again, or describe the thing. Help them without being asked, whenever the sentence shows \
it and the word is clear.

`focus` is the language the speaker is trying to speak in this sentence. `recent` holds the \
sentences just before it. `asked_about`, when present, is what the speaker asked how to say.
You judge `sentence` only. `recent` is there to understand it: every sentence in `recent` was \
judged when it was said, so never give a hint for a word or a mistake that is only in `recent` \
(the one exception is not_understood, below).

How a turn ends: the device closes a turn when the speaker has been silent for about half a \
second. So a sentence that simply stops ("I forgot my", "Do you have a.") was not cut by \
accident: the speaker stopped talking right there, usually because the next word would not come. \
"..." or "um" at the end mean the same.

`noticed`, when present, lists what a simple pattern detector saw in the sentence. It cannot \
understand the sentence, so these are clues, never verdicts; you decide.
- stops_short: it ends, or hesitates, right where a word should follow;
- starts_over: the speaker began the sentence several times before getting through it;
- describes: a general word (thing, place, coisa, lugar) stands with what the thing does or is for;
- searches: they look for the word aloud, often in their own language, in the middle of the \
sentence ("I need my, como é que fala, ...", "Preciso do, how do you say, para abrir a porta"). \
That aside is not what they want translated: the word they need is the one missing from the \
sentence around it, in the focus language;
- partner_lost: this speaker did not understand what was just said.

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
- asks_partner: the same, asked of another person by name. asks_mochi: asked of Mochi.
- trails_off: the turn stops, or hesitates, before a word, and what was said before the stop \
tells which word has to come. Read the WHOLE turn and `recent`, not only its last few words: the \
situation is usually named a moment earlier. "It's raining a lot and I forgot my" -> umbrella; \
"I need to cut this paper. Do you have a" -> scissors; "I cut my finger, do you have a" -> \
bandage; "It's too hot in here, can you turn on the" -> fan; "Está frio, vou pegar o meu, hum" \
-> casaco; after "I want to pay." in `recent`, "Can you bring the" -> bill. The test: would most \
people who heard it fill in the same word, or one of two or three? Then give the most likely \
word, with up to two more that fit as candidates. Only when nothing before the stop points to a \
word ("Can you pass me the" on its own, "And then I", "The one with cheese and") is there \
nothing to show: IGNORE.
- restarts: they begin the sentence two or three times and end up saying it the long way round \
because the one word for it would not come: "We should, we need to, we have to make the meeting \
later." -> postpone; "She is very, she is, she doesn't like to spend money." -> stingy; "I want \
to, I want, I need to give back this shirt." -> return. Someone who only repeats a word or \
corrects course ("I need to, sorry, I want to book a table.") needs nothing.
- talks_around: they name a thing, a person, an animal or a place by describing it, where the \
focus language has an everyday word every speaker would use instead: "the place where you buy \
medicine" -> pharmacy; "the doctor for the teeth" -> dentist; "the man who cuts the meat" -> \
butcher; "the parents of my wife" -> in-laws; "he never wants to work, he stays on the sofa all \
day" -> lazy; "o negócio de cortar papel" -> tesoura. Not when the description is simply the \
natural way to say it and no single word is being avoided: "the place where I grew up", "the \
guy who fixed my car", "the place where they sell those big sandwiches", "uma coisa que eu \
sempre quis fazer".
- look_alike: a false friend. Only when the request carries `suspect`; how to judge it is \
explained with it. Without `suspect`, never answer look_alike.
- not_understood: this speaker did not understand the one before ("Sorry, a what?", "What do you \
mean?", or their words repeated as a question), and `recent` shows what the problem was: a word \
of the other language, or a description standing in for a word. The hint is the word that \
earlier speaker needed, in the language of THEIR sentence in `recent` (an English sentence \
about "the place of the books" needs library, not biblioteca), and `meaning` is what they said \
instead. \
When `recent` is empty or was perfectly clear, IGNORE.

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
- anything where nothing in the sentence or `recent` narrows the word down: then you \
would only be guessing.

The transcript is made by a machine that expects one language, so a word of the other language \
is sometimes written the way it sounds, as a non-word or as several small words. Do not guess \
at such a word. If something in the sentence is no real word of either language and you cannot \
be sure which word it was, you cannot tell what was said: IGNORE. People also pause while they \
think, so a \
question can be split over two \
turns ("Como se fala..." and then "Carteira em inglês."): read `recent` to complete it. A \
question that stops before naming its word names nothing yet: IGNORE, never translate the \
question itself.

For SHOW_HINT give:
- "expression": the word they NEEDED, in the focus language: the translation they were looking \
for, never the word they said. One word or a short expression.
- "meaning": the word they said or meant, in the other language. When they said no word for it \
(trails_off, restarts, talks_around), the translation of `expression` into the other language.
- "example": their own sentence said correctly with the expression, in the focus language, at \
most about ten words. When they asked a question about the word, do not repeat the question: \
give a short everyday sentence that uses the expression.
- "confidence": from 0 to 1, how sure you are that the speaker is stuck and that this word, \
or one of the candidates, is the one they need.
- "meaning_language" and "expression_language": "en" or "pt-BR", the language each of the two is \
really written in. Be honest: `expression` must be in the focus language and `meaning` in the \
other one. If both turn out to be the same language, there is no hint: IGNORE.
- "candidates", only for trails_off, restarts or talks_around, and only when other words fit \
about as well: up to two MORE words, each {"expression", "meaning"}, same rules as above. Do not \
repeat `expression` in it. When one word is clearly it, and for every other reason, leave \
"candidates" out.

Reply with strict JSON only. To stay quiet, exactly {"decision": "IGNORE"} and no other field. \
For a hint: \
{"decision": "SHOW_HINT", "reason": <reason>, "meaning": <string or null>, "meaning_language": \
<"en"|"pt-BR">, "expression": <string>, "expression_language": <"en"|"pt-BR">, "confidence": \
<number>, "example": <string or null>, "candidates": <optional array>}.
Example, focus en: "Can you pass me the garfo, please?" -> {"decision": "SHOW_HINT", "reason": \
"code_switch", "meaning": "garfo", "meaning_language": "pt-BR", "expression": "fork", \
"expression_language": "en", "confidence": 0.95, "example": "Can you pass me the fork, please?"}.
Example, focus pt-BR: "Como se diz traffic jam em português?" -> {"decision": "SHOW_HINT", \
"reason": "says_unknown", "meaning": "traffic jam", "meaning_language": "en", "expression": \
"engarrafamento", "expression_language": "pt-BR", "confidence": 0.95, "example": "Fiquei preso \
num engarrafamento."}.
Example, focus en, noticed ["stops_short"]: "My hands are dirty, I need to wash them with" -> \
{"decision": "SHOW_HINT", "reason": "trails_off", "meaning": "sabão", "meaning_language": "pt-BR", \
"expression": "soap", "expression_language": "en", "confidence": 0.9, "example": "I need to wash \
them with soap.", "candidates": [{"expression": "water", "meaning": "água"}]}.
Example, focus pt-BR, noticed ["describes"]: "Eu fui no lugar onde você compra pão." -> \
{"decision": "SHOW_HINT", "reason": "talks_around", "meaning": "bakery", "meaning_language": "en", \
"expression": "padaria", "expression_language": "pt-BR", "confidence": 0.9, "example": "Eu fui \
na padaria."}.
Example, focus en, noticed ["stops_short"]: "Can you pass me the" -> {"decision": "IGNORE"}.
Example, focus en: "I need to go, ok? Tchau tchau!" -> {"decision": "IGNORE"}."""


NO_THINKING = "none"  # MOCHI_MODEL_REASONING_EFFORT for the gpt-5 family: answer at once
SUSPECT_THINKING = "low"  # ... except to confirm a suspected false friend (see `_sampling`)

# Sent only with a `suspect`. In the standing instructions its examples drew the model to a false
# friend in `recent` ("I pretend to travel..." two sentences back) instead of the sentence itself.
SUSPECT_NOTE = """`suspect` in the next message: a word list found, in `sentence`, a word that \
Portuguese and English speakers often use with the meaning of its look-alike in their own \
language. "used" is that word, "meant" the word probably meant, "look_alike" the word of their \
own language it resembles. Answer look_alike, with `expression` = "meant" and `meaning` = \
"look_alike", only if in THIS sentence "used" gives no sense or a strange one with its real \
meaning, and good sense with the meaning of "meant": "Yesterday I assisted a very good movie." \
(meant: watched), "He works in a fabric of cars." (meant: factory), "Estou muito excitado \
com a festa." (meant: animado). When the word is used \
correctly ("He assisted the doctor.", "This fabric is soft.", "I pretended to be asleep."), \
IGNORE. Everything else in your instructions still applies."""


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


def _sentence_json(request: ModelRequest) -> str:
    """What the model is shown of one request, as the JSON its instructions describe."""
    context: dict[str, JsonValue] = {
        "focus": request.focus.value,
        "recent": list(request.recent_texts),
        "sentence": request.text,
    }
    if request.asked_about:
        context["asked_about"] = request.asked_about
    if request.noticed:
        context["noticed"] = list(request.noticed)
    if request.suspect:
        context["suspect"] = request.suspect.model_dump()
    return json.dumps(context, ensure_ascii=False)


def _messages(request: ModelRequest) -> list[JsonValue]:
    """The standing instructions, the note for a suspected false friend if any, the sentence.

    The instructions come first and never change, so the provider's prompt cache holds them.
    Example: `_messages(request)[-1]["role"]` is "user".
    """
    messages: list[JsonValue] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if request.suspect:
        messages.append({"role": "system", "content": SUSPECT_NOTE})
    messages.append({"role": "user", "content": _sentence_json(request)})
    return messages


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
        self._base_url = base_url
        self._getter: HttpGetter | None = None

    def thinking(self, effort: str) -> "OpenAiHintModel":
        """Set `reasoning_effort` and return self: `OpenAiHintModel(...).thinking("none")`.

        The gpt-5 family thinks before it answers unless told not to, which is too slow for a
        hint; it also takes no `temperature`. Leave empty for models without the setting.
        """
        self._reasoning_effort = effort
        return self

    def warming(self, getter: HttpGetter) -> "OpenAiHintModel":
        """Let `warm_up` open connections through `getter`, and return self.

        It has to be the client that also posts, or the open connections are another pool's.
        Example: `OpenAiHintModel(http, url, "m", key, 2.0).warming(http)`.
        """
        self._getter = getter
        return self

    async def warm_up(self) -> None:
        """Open the connections a sentence will use (see `warm_start`). Never raises."""
        if self._getter is not None:
            await open_connections(self._getter, self._base_url, self._model_name, self._api_key)

    def logging(self, logger: EventLogger) -> "OpenAiHintModel":
        """Log a metadata-only line when a call fails, and return self.

        Example: `OpenAiHintModel(...).thinking("none").logging(logger)`.
        """
        self._logger = logger
        return self

    def _payload(self, request: ModelRequest) -> JsonValue:
        return {
            "model": self._model_name,
            **self._sampling(request),
            "response_format": {"type": "json_object"},
            "messages": _messages(request),
        }

    def _sampling(self, request: ModelRequest) -> dict[str, JsonValue]:
        if not self._reasoning_effort:
            return {"temperature": 0}
        if request.suspect and self._reasoning_effort == NO_THINKING:
            # Whether a word is used with its look-alike's meaning needs a moment of thought.
            # Measured on 9 sentences, 3 times each (D-42): 20 of 27 right answering at once,
            # 26 of 27 with "low", for 0.14 s more, and only sentences with a suspect pay it.
            return {"reasoning_effort": SUSPECT_THINKING}
        return {"reasoning_effort": self._reasoning_effort}

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
