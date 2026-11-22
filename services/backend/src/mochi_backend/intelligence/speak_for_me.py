"""Speak for me (DECISIONS D-64, changed by D-69): someone asks Mochi, by name, to speak for them.
From then on Mochi is the interpreter of the meeting: a sentence said in Portuguese it says aloud
in English, one said in English it says in Portuguese, whoever said it, until someone tells it
to stop.

The one case where Mochi speaks sentence after sentence without being called each time: the
people asked for exactly that, once. It does not need to know whose voice a sentence is (D-64
did, and spoke for that one person only): the language of the sentence says which way to go.
"""

import asyncio
import re
from collections import deque

from mochi_backend.intelligence.interpret_port import (
    Interpretation,
    InterpretModel,
    InterpretRequest,
)
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon, other_language
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.tokens import folded, normalized
from mochi_backend.intelligence.wake_phrase import has_wake_phrase, says_mochi
from mochi_contracts import (
    Decision,
    DecisionKind,
    Language,
    SessionContext,
    SessionMode,
    Speak,
    SpeakReason,
    Turn,
)

# Matched on accent-folded, lower-case text: speech-to-text drops accents and capitals at will.
_ON = re.compile(
    r"\b(?:speak|talk|translate|interpret)\s+for\s+(?:me|us)\b|\bbe\s+(?:my|our)\s+(?:voice|interpreter|translator)\b"
    r"|\bfal[ae]r?\s+por\s+(?:mim|nos|(?:a\s+)?gente)\b|\btraduz\w*\s+(?:pra|para)\s+(?:mim|nos|(?:a\s+)?gente)\b"
    r"|\bseja\s+(?:a\s+minha\s+voz|(?:o\s+)?(?:meu|nosso)\s+interprete)\b"
)
# Clear without Mochi's name: nobody says these to a colleague.
_OFF_PLAIN = re.compile(
    r"\bstop\s+(?:speaking|talking|translating)\s+for\s+(?:me|us)\b"
    r"|\bpar[ae]r?\s+de\s+(?:falar|traduzir)\s+por\s+(?:mim|nos|(?:a\s+)?gente)\b"
)
# Only with its name: "stop" alone may be meant for a person. Short on purpose, and unlike the
# words that turn it on: in a live session "para de falar por mim" was heard as "pode falar por
# mim", which asks for the opposite (D-64).
_OFF_NAMED = re.compile(
    r"\bthat'?s\s+enough\b|\bi(?:'ll|\s+will|\s+can)\s+speak\s+(?:for\s+)?myself\b"
    r"|\bpar[ae]r?\s+de\s+(?:falar|traduzir)\b|\bdeixa\s+que\s+eu\s+falo\b|\beu\s+mesm[oa]\s+falo\b"
)
# The short ones count only as the last thing said: "Mochi, pode parar" is a command, "Mochi,
# quando chega o relatório?" and "Mochi, como eu falo fila em inglês?" are questions.
_TAIL = r"(?:[\s,]+(?:now|please|thanks|thank\s+you|agora|por\s+favor|obrigad[oa]))*[\s.!?]*$"
_OFF_SHORT = re.compile(r"\b(?:stop|pode\s+parar|chega|eu\s+falo)" + _TAIL)
# The name as the recogniser mishears it ("Moji, pode parar", "Hey Moshe, stop"), and then the
# stop phrase and nothing else. "Pode parar." with no name at all is a sentence to translate.
_OFF_MISHEARD = re.compile(
    r"^(?:(?:hey|hi|oi|ei|ola|okay|ok)[\s,]+)?m[ou]\w{1,5}[\s,]+(?:stop|pode\s+parar|chega)" + _TAIL
)
# Both ways out are named to whoever asked in English: said with a Brazilian accent, "Mochi,
# stop" was heard as "Mochi está" in a live session; "Mochi, pode parar" was understood (D-64).
ON_LINES = {
    Language.EN: (
        "[mood happy] Okay, I'll translate for you. "
        "To stop, say: Mochi, stop, or Mochi, pode parar."
    ),
    Language.PT_BR: (
        "[mood happy] Combinado, eu traduzo para vocês. Para parar, diga: Mochi, pode parar."
    ),
}
OFF_LINES = {
    Language.EN: "Okay, over to you.",
    Language.PT_BR: "Combinado, agora é com vocês.",
}
_OWN_WORDS = 4  # how many of its own sentences Mochi remembers, to know them when they come back


def _named_stop(low: str) -> bool:
    """A sentence with Mochi's name in it that tells it to stop. Example: "mochi, pode parar"."""
    return bool(_OFF_NAMED.search(low) or _OFF_SHORT.search(low))


def _worth_saying(answer: Interpretation | None, heard: str) -> str | None:
    """The model's sentence when there is one and it is not just the same words back."""
    sentence = " ".join((answer.sentence or "").split()) if answer else ""
    if answer is None or answer.decision != "SAY" or not sentence:
        return None
    return None if normalized(sentence) == normalized(heard) else sentence


def _silent() -> Decision:
    return Decision(decision=DecisionKind.IGNORE, hint=None, speak=None, learning_events=[])


class SpeakForMe:
    """Example: `await mode.take(turn, context)` -> a SPEAK decision with the sentence said in
    the other language, or None when this turn is not its business.

    One per conversation: it holds whether Mochi is interpreting right now.
    """

    def __init__(
        self, model: InterpretModel, lexicon: Lexicon, settings: IntelligenceSettings
    ) -> None:
        self._model = model
        self._lexicon = lexicon
        self._enabled = settings.speak_for_me
        self._timeout = settings.model_timeout_seconds
        self._on = False
        self._last: Language | None = None  # the language of the last sentence it translated
        self._own: deque[str] = deque(maxlen=_OWN_WORDS)  # what it said itself, normalized

    def use(self, model: InterpretModel) -> None:
        """Ask this model from now on. Example: `mode.use(OpenAiInterpretModel(chat))`."""
        self._model = model

    def fresh_session(self) -> None:
        """A session begins: Mochi interprets for nobody until asked again."""
        self._on, self._last = False, None
        self._own.clear()

    @property
    def on(self) -> bool:
        """True while Mochi says every sentence in the other language."""
        return self._on

    async def take(self, turn: Turn, context: SessionContext) -> Decision | None:
        """The decision when this turn turns the mode on or off, or is a sentence to say in the
        other language; None for every other turn (the usual rules then apply)."""
        if not self._enabled or context.mode is not SessionMode.MEETING:
            return None
        low = folded(turn.text)
        named = says_mochi(turn.text) or has_wake_phrase(turn.text)
        # Off is looked for first: "para de falar por mim" holds the words that turn it on.
        if self._on and self._stops(low, named):
            return self._turn_off(turn)
        if named and _ON.search(low):
            return self._turn_on(turn)
        if not self._on or named:  # a sentence for Mochi is answered, not translated
            return None
        return await self._in_the_other_language(turn, context)

    @staticmethod
    def _stops(low: str, named: bool) -> bool:
        if _OFF_PLAIN.search(low) or _OFF_MISHEARD.search(low):
            return True
        return named and _named_stop(low)

    def _language(self, text: str, fallback: Language = Language.EN) -> Language:
        return spoken_language(text, self._lexicon, fallback)

    def _turn_on(self, turn: Turn) -> Decision:
        """Anyone may ask; Mochi answers in the language it was asked in."""
        self._on = True
        language = self._language(turn.text)
        return self._says(ON_LINES[language], language)

    def _turn_off(self, turn: Turn) -> Decision:
        """Anyone may stop it: better silent than talking over people who want to talk."""
        self._on = False
        language = self._language(turn.text)
        return self._says(OFF_LINES[language], language)

    def _says(self, text: str, language: Language) -> Decision:
        """A SPEAK decision, remembered: on a microphone that hears Mochi, its own sentence
        comes back as a turn and must not be translated back."""
        self._own.append(normalized(text.partition("] ")[2] or text))
        speak = Speak(text=text, language=language, reason=SpeakReason.ASKS_MOCHI)
        return Decision(decision=DecisionKind.SPEAK, hint=None, speak=speak, learning_events=[])

    async def _in_the_other_language(self, turn: Turn, context: SessionContext) -> Decision | None:
        """The sentence in the other language, to be spoken; silence when it is Mochi's own
        sentence coming back; None when there is nothing to say (a filler, a model that failed)."""
        if normalized(turn.text) in self._own:
            return _silent()
        # A short sentence with no telling word is taken to go on in the language before it.
        source = self._language(turn.text, self._last or context.focus)
        request = InterpretRequest(
            text=turn.text,
            recent_texts=[t.text for t in context.recent_turns[-3:]],
            source=source,
            target=other_language(source),
        )
        try:
            answer = await asyncio.wait_for(self._model.interpret(request), self._timeout)
        except Exception:  # noqa: BLE001 - saying nothing is always a safe answer
            return None
        sentence = _worth_saying(answer, turn.text)
        if sentence is None:
            return None
        self._last = source
        return self._says(sentence, request.target)
