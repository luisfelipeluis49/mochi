"""InterpretModel over any OpenAI-compatible chat-completions API. Never raises; None instead."""

import json

from pydantic import ValidationError

from mochi_backend.intelligence.interpret_port import Interpretation, InterpretRequest
from mochi_backend.intelligence.json_chat import JsonChat
from mochi_backend.platform.http_client import JsonValue

INTERPRET_PROMPT = """You are the interpreter of a work meeting between people who speak \
English and people who speak Brazilian Portuguese. They asked a device to translate for them: each \
sentence someone says in `source` is said aloud in `target`, in that person's place. You get ONE \
sentence someone just said, a machine transcript of speech, and write what the device says.

Say what THEY said, as they would say it themselves in a meeting: in the first person, natural \
and complete. Nothing added, nothing left out, nothing explained, no "he says" or "she means". \
Keep names, numbers, dates and product names as they are. Drop fillers and false starts ("é", \
"tipo", "um", "quer dizer"). A word of the other language inside the sentence ("I need to adiar \
my meeting") is translated with the rest. `recent` holds the sentences said just before, by \
anyone: use it only to understand what "it" or "that" refers to, never translate it.

There is nothing to say, and you answer NOTHING, when:
- the whole sentence is already in `target`: it needs no translation;
- it is only a filler, a noise or a single unclear word;
- it is said to the device and not to the meeting ("Mochi, ...").

Reply with strict JSON only: {"decision": "SAY", "sentence": <string>} or {"decision": "NOTHING"}.
Example, source pt-BR, target en, sentence "A gente precisa adiar o lançamento para a semana que \
vem." -> {"decision": "SAY", "sentence": "We need to postpone the launch to next week."}.
Example, source pt-BR, target en, recent ["Why is the integration delayed?"], sentence "Porque, \
é, a gente ainda precisa destravar a autenticação." -> {"decision": "SAY", "sentence": "Because \
we still need to unblock the authentication."}.
Example, source en, target pt-BR, sentence "I think we should talk to the supplier first." -> \
{"decision": "SAY", "sentence": "Acho que a gente deveria falar com o fornecedor primeiro."}.
Example, source pt-BR, target en, sentence "I agree with that." -> {"decision": "NOTHING"}."""


def parse_interpretation(content: str) -> Interpretation | None:
    """The model's JSON as an `Interpretation`; None when it is not the JSON asked for.

    Example: `parse_interpretation('{"decision": "NOTHING"}').decision` is "NOTHING".
    """
    try:
        return Interpretation.model_validate_json(content)
    except ValidationError:
        return None


def _question(request: InterpretRequest) -> str:
    asked: dict[str, JsonValue] = {
        "source": request.source.value,
        "target": request.target.value,
        "recent": list(request.recent_texts),
        "sentence": request.text,
    }
    return json.dumps(asked, ensure_ascii=False)


class OpenAiInterpretModel:
    """Example: `OpenAiInterpretModel(JsonChat(http, config, "interpret"))`; see `interpret`."""

    def __init__(self, chat: JsonChat) -> None:
        self._chat = chat

    async def warm_up(self) -> None:
        """Open the connections the first sentence will use. Never raises."""
        await self._chat.warm_up()

    async def interpret(self, request: InterpretRequest) -> Interpretation | None:
        """Ask the model; None on any failure or on output that is not the strict JSON."""
        messages: list[JsonValue] = [
            {"role": "system", "content": INTERPRET_PROMPT},
            {"role": "user", "content": _question(request)},
        ]
        content = await self._chat.ask(messages)
        return None if content is None else parse_interpretation(content)
