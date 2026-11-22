"""Someone asks to HEAR a word: the one time Mochi speaks without being called by name.

Seen live: "cortar o cabelo" was on the screen, then "você pode pronunciar para mim?" got
silence. A word on a screen does not tell how it sounds (DECISIONS D-30).
"""

import re
from datetime import timedelta

from mochi_backend.intelligence.tokens import lowered, normalized
from mochi_backend.platform.clock import parse_iso_z
from mochi_contracts import Hint, SessionContext, Turn

# An explicit request to HEAR a word or the shown hint said: "how do you pronounce X", "say it for
# me", "fala de novo". Not ordinary talk that merely contains "pronounce" or "fala pra mim":
# "Fala pra mim como foi a viagem" asks for a story. Not "say that again": people say that to
# each other when they did not catch something.
_OBJECT = r"(?:it|that|this|the word|that word)"
_PEDIDO = r"(?:isso|ela|a palavra|essa palavra)"
_WANTS_TO_HEAR = re.compile(
    r"\bhow (?:do|does|would|should|can|could) (?:you|i|we|one|it|that|this)\b[^?.!]{0,12}"
    r"\bpronounc\w*|\bhow (?:is|are) [^?.!]{1,30}\bpronounced\b|"
    rf"\b(?:can|could|would|will) you (?:please )?pronounce\b|\bpronounce {_OBJECT}\b|"
    r"\bwhat(?:'s| is) the pronunciation\b|\bhow does (?:it|that) sound\b|"
    rf"\bsay (?:it|that|this|the word) (?:out loud|aloud|for me|for us)\b|"
    r"\bsay (?:the word|it) again\b|\blet me hear (?:it|that)\b|\bem voz alta\b|"
    r"\bcomo (?:se pronuncia|pronuncia|pronunciar)\b|"
    r"\b(?:como [e\u00e9]|qual [e\u00e9]) a pron[u\u00fa]nci\w+|"
    r"\b(?:pode|poderia|consegue|sabe) pronunciar\b|\bpronuncia (?:isso|ela|a palavra)\b|"
    rf"\b(?:fala|falar|diz|dizer|repete|repetir) (?:{_PEDIDO} )?(?:de novo|novamente|outra vez)\b|"
    rf"\b(?:repete|repetir) {_PEDIDO}\b|"
    r"\b(?:fala|falar|diz|dizer|repete|repetir)\b[^?.!]{0,30}"
    r"\b(?:para|pra) (?:mim|n[o\u00f3]s|a gente)\s*(?:de novo|novamente|outra vez)?\s*[?.!]*\s*$"
)
# Telling someone that one asked is not asking. Seen live: "eu perguntei explicitamente como se
# pronuncia", said to the partner half a minute after a hint, made Mochi say that hint aloud.
_REPORTED = re.compile(
    r"\b(?:i|we|she|he|they) (?:just |already |explicitly )*(?:asked|said|told|wanted)\b|"
    r"\b(?:perguntei|perguntou|perguntamos|pedi|pediu|pedimos|falei|disse)\b|"
    # seen live (D-70): "I'm not even going to ask you to pronounce it for me" was pronounced
    r"(?:\bnot|n't|\bnever)\s+(?:even\s+)?(?:(?:going|want|need|have)\s+to\s+|gonna\s+)?"
    r"(?:ask|pronounce|say|hear)\b|"
    r"\bn[aã]o (?:precisa|quero que|vou pedir)\s+(?:\w+\s+){0,2}"
    r"(?:pronunci\w+|fal\w+|diz\w+|repet\w+)"
)
# Saying that one will repeat oneself is not asking Mochi to. Seen live (D-69): "I'll say it
# again: can you send me the plan before lunch?" made Mochi say the last hint aloud, four times.
_ONESELF = re.compile(
    r"\b(?:i'll|i will|i'm going to|i am going to|i'm gonna|i have to|i need to|let me|let's"
    r"|we'll|we will|want me to)\s+(?:just\s+)?say (?:it|that|this|the word)\b|"
    r"\b(?:vou|vamos|vai|tenho que|preciso|deixa eu|deixa que eu|quer que eu) "
    r"(?:falar|dizer|repetir)\b"
)
# A word the recogniser put in quotes: "Você pode falar 'reunião' para mim?"
_QUOTED = re.compile(r"[\"“]([^\"”]{2,40})[\"”]|(?<!\w)['‘]([^'’]{2,40})['’](?!\w)")


def wants_to_hear(text: str) -> bool:
    """True when the turn asks how a word sounds. Example: "Can you pronounce it?" -> True.

    Not when it tells about having asked ("I asked how it is pronounced"), nor when the speaker
    is going to repeat themselves ("I'll say it again").
    """
    said = lowered(text)
    if _REPORTED.search(said) or _ONESELF.search(said):
        return False
    return _WANTS_TO_HEAR.search(said) is not None


def _quoted(text: str) -> str | None:
    found = _QUOTED.search(text)
    return (found.group(1) or found.group(2)).strip() if found else None


def _last_hint(context: SessionContext, turn: Turn, window: timedelta) -> Hint | None:
    """The newest hint still fresh at `turn`: it left the screen at most `window` ago."""
    heard = parse_iso_z(turn.received_at)
    fresh = [h for h in context.recent_hints if heard - parse_iso_z(h.expires_at) <= window]
    return fresh[-1] if fresh else None


def word_to_hear(turn: Turn, context: SessionContext, window_seconds: float) -> Hint | str | None:
    """What to say aloud for a turn that `wants_to_hear`: a recent hint, a quoted word, or None.

    A quoted word wins unless it is the hint's own word or the word the hint stands for:
    "a pronúncia de 'cut my hair'?" after the hint "cortar o cabelo" wants the Portuguese.
    Example: hint "fork" shown a minute ago, "Can you pronounce it?" -> that hint.
    """
    hint = _last_hint(context, turn, timedelta(seconds=window_seconds))
    named = _quoted(turn.text)
    if named is None or hint is None:
        return named or hint
    of_the_hint = {normalized(hint.expression), normalized(hint.meaning or "")}
    return hint if normalized(named) in of_the_hint else named
