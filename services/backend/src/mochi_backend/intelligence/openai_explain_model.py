"""ExplainModel over any OpenAI-compatible chat-completions API. Never raises; None instead."""

import json

from pydantic import ValidationError

from mochi_backend.intelligence.explain_port import ExplainRequest, Explanation
from mochi_backend.intelligence.json_chat import JsonChat
from mochi_backend.platform.http_client import JsonValue

EXPLAIN_PROMPT = """You are the silent helper inside a device that sits in work meetings where \
people speak English and Brazilian Portuguese. Some of the people listening are still learning \
the language being spoken: they follow everyday talk and common work vocabulary, about \
intermediate level. You read ONE sentence at a time, a machine transcript of speech, and decide \
whether it contains an expression those listeners would probably not understand, so that the \
device can quietly show what it means. Most sentences contain nothing of the kind, and an \
explanation nobody needed is a distraction in a meeting: when in doubt, IGNORE.

`language` is the language the sentence is in. `explain_in` is the listeners' own language. \
`recent` holds the sentences just before it, only to understand the sentence: never explain \
something that is only in `recent`.

EXPLAIN at most one expression, the hardest one, and only if it is one of these:
- idiom: an idiom or figurative expression, also a figurative business phrase, whose meaning \
cannot be worked out from its words: "circle back", "low-hanging fruit", "touch base", "on the \
same page", "move the needle", "table this", "a ballpark figure", "bite the bullet", "the elephant \
in the room", "dar um jeito", "bater o martelo", "quebrar o galho", "ficar de olho", "em cima da \
hora", "pisar na bola". A phrasal verb counts only when its meaning is far from its words ("we \
need to iron this out", "let's wrap up"), never an everyday one ("find out", "set up", "come \
back", "go on"). Slang counts too, also a single word, when it is used with a meaning its \
everyday sense does not give: "I'm swamped this week" (very busy), "the new design is fire" \
(excellent), "that's a no-brainer", "essa semana tá puxada" (hard), "ele ficou enrolando" \
(stalling), "deu ruim" (it went wrong).
- technical_term: a term of a trade or a field, or an abbreviation, that someone outside that \
field would not know: "churn rate", "technical debt", "rollback", "EBITDA", "accrual", \
"idempotent", "burn rate", "SLA", "run rate", "fluxo de caixa", "inadimplência", "homologação". \
Not the words common in any office (meeting, deadline, budget, report, team, project, feedback, \
email, reunião, prazo, orçamento, relatório).

IGNORE all of this:
- ordinary words, also formal or less frequent ones (postpone, schedule, approve, agendar, \
providenciar): you are not a dictionary;
- names of people, companies, products and places;
- a word of the other language dropped into the sentence (something else handles that);
- anything you are not sure you read right: the transcript is made by a machine, and a strange \
word is more often a mishearing than a rare term;
- a sentence said to the device itself ("Mochi, ...").

For EXPLAIN give:
- "kind": "idiom" or "technical_term";
- "expression": the expression exactly as it stands in the sentence, in the same words, without \
the words around it (at most five words);
- "meaning": what it means here, in `explain_in`, in at most six words: the usual translation \
where there is one, otherwise a short description;
- "plain": the same thing in plain everyday words of `language`, at most six words;
- "confidence": from 0 to 1, how sure you are that an intermediate learner would not understand \
it AND that your meaning is right in this sentence.

Reply with strict JSON only. To stay quiet, exactly {"decision": "IGNORE"} and no other field. \
Otherwise {"decision": "EXPLAIN", "kind": <kind>, "expression": <string>, "meaning": <string>, \
"plain": <string>, "confidence": <number>}.
Example, language en, explain_in pt-BR: "Let's circle back on pricing after the launch." -> \
{"decision": "EXPLAIN", "kind": "idiom", "expression": "circle back", "meaning": "voltar ao \
assunto depois", "plain": "talk about it again later", "confidence": 0.9}.
Example, language en, explain_in pt-BR: "Our churn rate went up again this quarter." -> \
{"decision": "EXPLAIN", "kind": "technical_term", "expression": "churn rate", "meaning": "taxa \
de cancelamento de clientes", "plain": "share of customers who leave", "confidence": 0.85}.
Example, language pt-BR, explain_in en: "A gente precisa bater o martelo sobre o fornecedor \
hoje." -> {"decision": "EXPLAIN", "kind": "idiom", "expression": "bater o martelo", "meaning": \
"make the final decision", "plain": "decidir de vez", "confidence": 0.9}.
Example, language en, explain_in pt-BR: "Can you send me the report before the meeting \
tomorrow?" -> {"decision": "IGNORE"}.
Example, language en, explain_in pt-BR: "We need to postpone the review to next week." -> \
{"decision": "IGNORE"}."""


def _confidence(value: object) -> float | None:
    """The model's confidence as 0-1; a percentage is scaled, anything else is no statement."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value / 100 if value > 1 else float(value)


def parse_explanation(content: str) -> Explanation | None:
    """The model's JSON as an `Explanation`; None when it is not the JSON that was asked for.

    Example: `parse_explanation('{"decision": "IGNORE"}').decision` is "IGNORE".
    """
    try:
        fields = json.loads(content)
        if not isinstance(fields, dict):
            return None
        fields["confidence"] = _confidence(fields.get("confidence"))
        return Explanation.model_validate(fields)
    except (ValueError, ValidationError):
        return None


def _question(request: ExplainRequest) -> str:
    asked: dict[str, JsonValue] = {
        "language": request.language.value,
        "explain_in": request.explain_in.value,
        "recent": list(request.recent_texts),
        "sentence": request.text,
    }
    return json.dumps(asked, ensure_ascii=False)


class OpenAiExplainModel:
    """Example: `OpenAiExplainModel(JsonChat(http, config, "explain"))`; see `explain`."""

    def __init__(self, chat: JsonChat) -> None:
        self._chat = chat

    async def warm_up(self) -> None:
        """Open the connections the first sentence will use. Never raises."""
        await self._chat.warm_up()

    async def explain(self, request: ExplainRequest) -> Explanation | None:
        """Ask the model; None on any failure or on output that is not the strict JSON."""
        messages: list[JsonValue] = [
            {"role": "system", "content": EXPLAIN_PROMPT},
            {"role": "user", "content": _question(request)},
        ]
        content = await self._chat.ask(messages)
        return None if content is None else parse_explanation(content)
