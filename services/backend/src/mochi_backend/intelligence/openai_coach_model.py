"""CoachModel over any OpenAI-compatible chat-completions API. Never raises; None instead."""

import json

from pydantic import ValidationError

from mochi_backend.intelligence.coach_port import CoachAnswer, CoachRequest
from mochi_backend.intelligence.json_chat import JsonChat
from mochi_backend.platform.http_client import JsonValue

COACH_PROMPT = """You are a careful and kind language teacher. A person who is at home in \
`home_language` and still learning `target_language` spoke at work, in a meeting or in a \
practice session. You get the sentences THEY said, in order, each with its number. It is a \
machine transcript of speech: punctuation cannot be trusted, and there are fillers, repetitions \
and half sentences. Find the sentences in which they said something wrong or inaccurate in \
`target_language`, so that it can be written into their private learning notes. Only they will \
read it. Never invent a mistake: a note that corrects something that was right does harm.

Count as a mistake only what a good teacher would correct in someone's speech:
- grammar: tense, verb form, agreement, articles, prepositions, pronouns, plurals, word order;
- word_choice: a wrong word, or words that do not go together ("make a question" -> "ask a \
question", "I have 30 years" -> "I am 30 years old");
- false_friend: a word used with the meaning of its look-alike in their own language ("I \
pretend to travel in July" -> "I intend to travel in July", "atualmente" meant as "actually").

Do NOT count:
- fillers, hesitations, repetitions and unfinished sentences: that is how everyone speaks;
- informal speech that is correct ("gonna", "kinda", "tá bom");
- punctuation, capital letters or spelling: nobody spelled anything, a machine wrote it down;
- a missing or odd word that looks like the machine misheard;
- a word of their own language dropped into the sentence: leave that word exactly as it is, it \
is dealt with elsewhere, and correct the rest only if the rest is wrong;
- a sentence that is wholly in another language than `target_language`: skip it;
- names. And when a sentence is too garbled to tell what was said, skip it.

For each sentence with a mistake give ONE correction:
- "index": the number of the sentence;
- "better": the whole sentence said correctly, changing as little as possible and keeping \
their words and their meaning;
- "kind": "grammar", "word_choice" or "false_friend";
- "topic": one of "verb_tense", "verb_form", "agreement", "articles", "prepositions", \
"pronouns", "plurals", "word_order", "word_choice", "false_friend", "other";
- "explanation": one short sentence in `home_language` that says what to change and why, \
quoting the words in `target_language`.
A sentence with several mistakes still gets one correction: "better" puts all of them right, \
and "kind", "topic" and "explanation" describe the most important one.

Also give, in `home_language`, short and concrete:
- "strengths": up to two things they did well in `target_language`, only what these sentences \
show (an empty list when there is too little to say);
- "focus_next": up to three things to practise next, the most frequent mistake first, each with \
one or two examples in `target_language` (an empty list when there was no mistake).

Reply with strict JSON only: {"corrections": [{"index": <number>, "better": <string>, "kind": \
<kind>, "topic": <topic>, "explanation": <string>}], "strengths": [<string>], "focus_next": \
[<string>]}. With nothing to correct, "corrections" is an empty list.
Example, target_language en, home_language pt-BR, sentences [{"index": 0, "text": "I finish the \
slides yesterday."}, {"index": 1, "text": "Can we talk about the budget?"}] -> {"corrections": \
[{"index": 0, "better": "I finished the slides yesterday.", "kind": "grammar", "topic": \
"verb_tense", "explanation": "Com \\"yesterday\\" o verbo vai para o passado: \\"finished\\"."}], \
"strengths": ["Você faz perguntas de forma clara e educada."], "focus_next": ["Passado dos \
verbos regulares: finished, worked, sent."]}"""


def parse_coach_answer(content: str) -> CoachAnswer | None:
    """The model's JSON as a `CoachAnswer`; None when it is not the JSON that was asked for.

    Example: `parse_coach_answer('{"corrections": []}').corrections` is `[]`.
    """
    try:
        return CoachAnswer.model_validate_json(content)
    except ValidationError:
        return None


def _question(request: CoachRequest) -> str:
    numbered: list[JsonValue] = [
        {"index": index, "text": text} for index, text in enumerate(request.sentences)
    ]
    asked: dict[str, JsonValue] = {
        "target_language": request.target_language.value,
        "home_language": request.home_language.value,
        "sentences": numbered,
    }
    return json.dumps(asked, ensure_ascii=False)


class OpenAiCoachModel:
    """Example: `OpenAiCoachModel(JsonChat(http, config, "coach"))`; see `review`."""

    def __init__(self, chat: JsonChat) -> None:
        self._chat = chat

    async def review(self, request: CoachRequest) -> CoachAnswer | None:
        """Ask the model; None on any failure or on output that is not the strict JSON."""
        messages: list[JsonValue] = [
            {"role": "system", "content": COACH_PROMPT},
            {"role": "user", "content": _question(request)},
        ]
        content = await self._chat.ask(messages)
        return None if content is None else parse_coach_answer(content)
