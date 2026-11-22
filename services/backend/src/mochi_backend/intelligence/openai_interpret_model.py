"""InterpretModel over any OpenAI-compatible chat-completions API. Never raises; None instead."""

import json

from pydantic import ValidationError

from mochi_backend.intelligence.interpret_port import Interpretation, InterpretRequest
from mochi_backend.intelligence.json_chat import JsonChat
from mochi_backend.platform.http_client import JsonValue

INTERPRET_PROMPT = """You are the interpreter of a work meeting between people who speak \
English and people who speak Brazilian Portuguese. They asked a device to translate for them: each \
sentence someone says in one of the two languages is said aloud in the other, in that person's \
place. You get ONE sentence someone just said, a machine transcript of speech, and write what the \
device says.

`source` is a guess of the language the sentence is in, made by counting its small words, and \
`target` the other one. For a short sentence the guess is often wrong ("Quanto custa?", "Sounds \
good."). Decide yourself which language the sentence is in, and say it in the OTHER one; give \
the language of YOUR sentence in `language` ("en" or "pt-BR"). A sentence with a borrowed word \
("I need to adiar my meeting") is in the language of the rest of it, and the borrowed word is \
translated with it.

Say what THEY said, as they would say it themselves in a meeting: in the first person, natural \
and complete. Nothing added, nothing left out, nothing explained, no "he says" or "she means". \
Keep names, numbers, dates and product names as they are. Drop fillers and false starts ("é", \
"tipo", "um", "quer dizer"). `recent` holds the sentences said just before, by anyone: use it \
only to understand what "it" or "that" refers to, never translate it.

There is nothing to say, and you answer NOTHING, when:
- it is only a filler, a noise or a single unclear word;
- it is said to the device and not to the meeting ("Mochi, ...").

Reply with strict JSON only: {"decision": "SAY", "language": <"en" or "pt-BR">, "sentence": \
<string>} or {"decision": "NOTHING"}.
Example, source pt-BR, target en, sentence "A gente precisa adiar o lançamento para a semana que \
vem." -> {"decision": "SAY", "language": "en", "sentence": "We need to postpone the launch to \
next week."}.
Example, source pt-BR, target en, recent ["Why is the integration delayed?"], sentence "Porque, \
é, a gente ainda precisa destravar a autenticação." -> {"decision": "SAY", "language": "en", \
"sentence": "Because we still need to unblock the authentication."}.
Example, source en, target pt-BR, sentence "I think we should talk to the supplier first." -> \
{"decision": "SAY", "language": "pt-BR", "sentence": "Acho que a gente deveria falar com o \
fornecedor primeiro."}.
Example, source en, target pt-BR (the guess is wrong), sentence "Quanto custa?" -> \
{"decision": "SAY", "language": "en", "sentence": "How much does it cost?"}.
Example, source pt-BR, target en, sentence "Hum, é." -> {"decision": "NOTHING"}."""


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
