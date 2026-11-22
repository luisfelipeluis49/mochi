"""PhraseModel over any OpenAI-compatible chat-completions API. Never raises; None instead."""

import json

from pydantic import ValidationError

from mochi_backend.intelligence.json_chat import JsonChat
from mochi_backend.intelligence.phrase_port import PhraseAnswer, PhraseRequest
from mochi_backend.platform.http_client import JsonValue

PHRASE_PROMPT = """You help someone say what they mean in a work meeting. They are speaking \
`language` (English or Brazilian Portuguese), which they are still learning, and got stuck in \
the middle of a sentence: they switched to their own language, asked how to say a word, \
stopped, started again, or talked around it. A device has already shown them the one word they \
needed (`word`; `said` is what they said instead, when they said something). You write the \
whole sentence they were trying to say, so that with one touch the device can say it aloud for \
them and the meeting goes on.

`sentence` is a machine transcript of what they said. `recent` holds the sentences just before \
it, often the question they are answering: use it to understand what they mean, not to add to it.

Write ONE sentence in `language`:
- what THEY meant, complete and natural, the way a colleague at home in `language` would say \
it in a meeting; use `word` where it belongs;
- nothing they did not say: no new facts, no reasons, no politeness they did not use;
- without the asides in which they looked for the word ("como é que fala", "how do you say", \
"um", the false starts);
- short: at most about sixteen words.
When `sentence` was a question about a word ("how do you say fila in English?") and not an \
attempt to say something, or when you cannot tell what they meant, there is nothing to say for \
them: IGNORE.

Reply with strict JSON only: {"decision": "SUGGEST", "sentence": <string>} or \
{"decision": "IGNORE"}.
Example, language en, recent ["Why is the integration delayed?"], word "unblock", said \
"destravar", sentence "Because we need to, como é que fala, destravar a autenticação." -> \
{"decision": "SUGGEST", "sentence": "Because we need to unblock the authentication process."}.
Example, language en, recent [], word "postpone", said "adiar", sentence "I need to adiar my \
meeting tomorrow." -> {"decision": "SUGGEST", "sentence": "I need to postpone my meeting \
tomorrow."}.
Example, language pt-BR, recent ["Você trouxe tudo?"], word "guarda-chuva", said "umbrella", \
sentence "Eu esqueci meu umbrella no escritório." -> {"decision": "SUGGEST", "sentence": "Eu \
esqueci meu guarda-chuva no escritório."}.
Example, language en, recent [], word "queue", said "fila", sentence "How do you say fila in \
English?" -> {"decision": "IGNORE"}."""


def parse_phrase(content: str) -> PhraseAnswer | None:
    """The model's JSON as a `PhraseAnswer`; None when it is not the JSON that was asked for.

    Example: `parse_phrase('{"decision": "IGNORE"}').decision` is "IGNORE".
    """
    try:
        return PhraseAnswer.model_validate_json(content)
    except ValidationError:
        return None


def _question(request: PhraseRequest) -> str:
    asked: dict[str, JsonValue] = {
        "language": request.language.value,
        "recent": list(request.recent_texts),
        "word": request.word,
        "said": request.said,
        "sentence": request.text,
    }
    return json.dumps(asked, ensure_ascii=False)


class OpenAiPhraseModel:
    """Example: `OpenAiPhraseModel(JsonChat(http, config, "phrase"))`; see `phrase`."""

    def __init__(self, chat: JsonChat) -> None:
        self._chat = chat

    async def warm_up(self) -> None:
        """Open the connections the first sentence will use. Never raises."""
        await self._chat.warm_up()

    async def phrase(self, request: PhraseRequest) -> PhraseAnswer | None:
        """Ask the model; None on any failure or on output that is not the strict JSON."""
        messages: list[JsonValue] = [
            {"role": "system", "content": PHRASE_PROMPT},
            {"role": "user", "content": _question(request)},
        ]
        content = await self._chat.ask(messages)
        return None if content is None else parse_phrase(content)
