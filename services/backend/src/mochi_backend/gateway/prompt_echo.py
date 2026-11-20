"""Speech-to-text that is given a prompt sometimes writes the prompt into the transcript.

Seen live with OpenAI transcription: a sentence arrived as "Como você falar Mochi, adiar, postpone,
guarda-chuva, umbrella, recibo, ... Esqueci a palavra." The run of expected words is the prompt's
own list, not something anyone said, and it would make the hint rules see words nobody used.
"""

import re

MIN_RUN = 4  # this many expected words in a row, with nothing between them, is the list


def without_prompt_echo(text: str, prompt: str, words: tuple[str, ...]) -> str:
    """The transcript without a pasted-in prompt: its sentences, or a run of its word list.

    Example: `without_prompt_echo("So Mochi, adiar, postpone, fila, queue. I forgot.", "", words)`
    is "So I forgot." A single expected word in a sentence is left alone.
    """
    cleaned = text
    for sentence in filter(None, (part.strip() for part in re.split(r"(?<=[.;:])\s+", prompt))):
        cleaned = re.sub(re.escape(sentence), " ", cleaned, flags=re.IGNORECASE)
    if words:
        one = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
        run = rf"(?:(?<!\w)(?:{one})(?!\w)[\s,.;]*){{{MIN_RUN},}}"
        cleaned = re.sub(run, " ", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())
