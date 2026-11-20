"""HintModel over any OpenAI-compatible chat-completions API. Never raises; returns None instead."""

import json

from pydantic import BaseModel, ValidationError

from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion
from mochi_backend.platform.http_client import HTTP_OK, HttpClient, HttpTransportError, JsonValue
from mochi_contracts import Reason

SYSTEM_PROMPT = (
    "Two people practise a language by talking to each other. One is at home in Brazilian "
    "Portuguese and practising English; the other is at home in English and practising Brazilian "
    "Portuguese. Judge ONE sentence in context: is the speaker stuck on a word or short "
    "expression? `focus` is the language they are trying to speak in this sentence.\n"
    "Reasons: code_switch (a word or phrase of their own language dropped into the sentence "
    "because they did not know it in the focus language), says_unknown (says they do not know "
    "the word, or asks how to say it), asks_partner, asks_mochi, trails_off, talks_around "
    "(describes the thing instead of naming it), restarts, look_alike (a false friend: a word "
    "that looks like one of their own language but means something else here), not_understood.\n"
    "Say IGNORE for: ordinary sentences, thinking aloud, self-corrections, deliberate switches "
    "(names, dishes, places, brands), grammar slips such as a wrong tense (this is about words, "
    "never grammar), personal or serious talk, and anything about a third language.\n"
    "For SHOW_HINT: `expression` is the word they NEEDED, in the focus language: the translation "
    "they were looking for, never the word they said. `meaning` is the word they said or meant, "
    "in the other language. Both are one word or a short expression. `example` is one short "
    "sentence in the focus language that uses the expression.\n"
    "When `asked_about` is given, the speaker asked how to say exactly that: the hint is for it "
    "and for nothing else in the sentence, and the reason is says_unknown. People pause while "
    "they think, so a question can be "
    'split over two turns ("Como se fala..." and then "Carteira em inglês."): read '
    "`recent` to complete it. If you cannot tell which word they need, say IGNORE; never guess "
    "a word nobody mentioned or described.\n"
    'Reply with strict JSON only: {"decision": "IGNORE"|"SHOW_HINT", "reason": <reason or null>, '
    '"expression": <string or null>, "meaning": <string or null>, "example": <string or null>}.\n'
    'Example, focus en: "Can you pass me the garfo, please?" -> {"decision": "SHOW_HINT", '
    '"reason": "code_switch", "expression": "fork", "meaning": "garfo", "example": "Can you '
    'pass me the fork?"}. Example, focus pt-BR: "Como se diz traffic jam em português?" -> '
    '{"decision": "SHOW_HINT", "reason": "says_unknown", "expression": "engarrafamento", '
    '"meaning": "traffic jam", "example": "Fiquei preso num engarrafamento."}.'
)


def _suggestion(content: str, asked: bool) -> ModelSuggestion:
    """Parse the model's JSON. A reason it made up must not cost the whole answer.

    Seen with a real model: `"reason": "asked_about"` for an explicit question, which is not one of
    ours. For a question that named its word the reason is says_unknown; otherwise there is none.
    """
    fields = json.loads(content)
    if isinstance(fields, dict) and fields.get("reason") not in {r.value for r in Reason}:
        fields["reason"] = Reason.SAYS_UNKNOWN.value if asked else None
    return ModelSuggestion.model_validate(fields)


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _ChatReply(BaseModel):
    choices: list[_Choice]


class OpenAiHintModel:
    """Example: `OpenAiHintModel(http, base_url, "model", key, 2.0)`; see `suggest`."""

    def __init__(
        self, http: HttpClient, base_url: str, model_name: str, api_key: str, timeout_seconds: float
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._model_name = model_name
        self._api_key = api_key
        self._timeout = timeout_seconds

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
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        }

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """Ask the model; None on transport error, non-200, or output that is not strict JSON."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            reply = await self._http.post_json(
                self._url, headers, self._payload(request), self._timeout
            )
            if reply.status != HTTP_OK:
                return None
            content = _ChatReply.model_validate_json(reply.body).choices[0].message.content
            return _suggestion(content, asked=bool(request.asked_about))
        except (HttpTransportError, ValidationError, IndexError, ValueError):
            return None
