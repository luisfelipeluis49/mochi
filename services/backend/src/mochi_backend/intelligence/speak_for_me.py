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
from datetime import timedelta

from mochi_backend.intelligence.answer_checks import language_named
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
from mochi_backend.platform.clock import parse_iso_z
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
# "Mochi, você pode traduzir?", "Mochi, can you translate?", "Mochi, traduz, por favor": Mochi is
# asked to translate, and nothing to translate follows. Seen live (D-70): that is how it was
# asked, and nothing happened. Only as a request: "Mochi, como se diz traduzir?", "Mochi, that
# was hard to translate" and "Mochi, can you translate fila?" are not.
_ON_BARE = re.compile(
    r"(?:\b(?:can|could|would|will)\s+you\s+(?:please\s+)?(?:translate|interpret)"
    r"|\b(?:pode|poderia|consegue|da\s+pra)\s+(?:traduzir|interpretar)"
    r"|(?:^|[.,!?]\s*)(?:please\s+|por\s+favor[,\s]+)?(?:translate|traduz|traduza|interpreta))"
    r"(?:[\s,]+(?:please|now|everything|the\s+(?:meeting|conversation)|por\s+favor|agora|tudo"
    r"|a\s+(?:reuniao|conversa)))*\s*(?:[.!?]|$)"
)
_CALL_LASTS = timedelta(seconds=12)  # how long after "Mochi, ..." the next sentence may ask it
_CALL_WORDS = 5  # ... and how short that sentence is: "Traduzir pra gente?", not a remark
# Not asking: "Mochi, don't translate for us", "não precisa falar por mim", "I asked Mochi to
# speak for me yesterday". With the words that turn it on, these mean stop, or nothing.
_NOT_ASKING = re.compile(
    r"\b(?:don'?t|do\s+not|doesn'?t|didn'?t|not|no\s+need|never|nao|nunca|sem"
    r"|asked|told|said|pedi\w*|falei|disse)\b"
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
    r"|\bstop\s+(?:speaking|talking|translating|interpreting)\b"
    r"|\bpar[ae]r?\s+de\s+(?:falar|traduzir)\b|\bdeixa\s+que\s+eu\s+falo\b|\beu\s+mesm[oa]\s+falo\b"
)
# Mochi's name as the recogniser writes it: Mochi, Moshi, Moji, Motchi, Moshe, Muchi.
_NAME = r"m(?:o(?:ch|sh|tch|tsh|j|x|g)\w{0,3}|uch[iy]|ouch\w*)"
# The short ones count only where a sentence ends: "Mochi, pode parar." and "Stop, Mochi" are
# commands, also with more said after them; "Mochi, quando chega o relatório?" and "Mochi, how
# do you say stop sign?" are questions.
_POLITE = (
    r"(?:[\s,]+(?:now|please|thanks|thank\s+you|okay|ok|agora|por\s+favor|obrigad[oa]|ta\s+bom"
    rf"|valeu|{_NAME}))*"
)
_ENDS = r"\s*(?:[.!?]|$)"
_OFF_SHORT = re.compile(r"\b(?:stop|pode\s+parar|par[ae]|chega)" + _POLITE + _ENDS)
# The name misheard beyond what `says_mochi` knows ("Moji, pode parar", "Hey Moshe, stop"), and
# then the stop phrase. "Pode parar." with no name at all is a sentence to translate.
_OFF_MISHEARD = re.compile(
    rf"^(?:(?:hey|hi|oi|ei|ola|okay|ok)[\s,]+)?{_NAME}[\s,.]+(?:stop|pode\s+parar|chega)"
    + _POLITE
    + _ENDS
)
_SENTENCE_END = re.compile(r"[.!?]+\s*")
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
_OWN_WORDS = 12  # the pieces of its own last lines Mochi remembers, to know them coming back


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
        if self._on and normalized(turn.text) in self._own:
            return _silent()  # its own voice, heard by a microphone: not a command, not a sentence
        low = folded(turn.text)
        named = says_mochi(turn.text) or has_wake_phrase(turn.text)
        command = self._command(turn, low, named, self._follows_a_call(turn, context))
        if command is not None or not self._on or named:
            return command  # a sentence for Mochi is answered, not translated
        return await self._in_the_other_language(turn, context)

    def _command(self, turn: Turn, low: str, named: bool, called: bool) -> Decision | None:
        """What this turn does to the mode. Off is looked for first: "para de falar por mim"
        holds the words that turn it on, and so does "don't translate for us". `called`: the
        sentence before this one was for Mochi ("Mochi, pode traduzir?" "Traduzir pra gente?")."""
        asks = (named or called) and _ON.search(low) is not None
        asks = asks or (named and _ON_BARE.search(low) is not None)
        if self._stops(low, named) or (asks and _NOT_ASKING.search(low)):
            return self._turn_off(turn) if self._on else None
        if asks and self._on and not named:
            return _silent()  # "Traduzir pra gente?" after it said yes: asked and answered
        return self._turn_on(turn) if asks else None

    def _follows_a_call(self, turn: Turn, context: SessionContext) -> bool:
        """True for a short sentence said right after one that called Mochi and was not itself
        a stop ("Mochi, me ajuda?" ... "Traduzir pra gente?"). Not after "Mochi, pode parar":
        "Viu? Ele estava traduzindo pra gente." turned it on again."""
        if not context.recent_turns or len(turn.text.split()) > _CALL_WORDS:
            return False
        before = context.recent_turns[-1]
        soon = parse_iso_z(turn.received_at) - parse_iso_z(before.received_at) <= _CALL_LASTS
        called = says_mochi(before.text) or has_wake_phrase(before.text)
        return soon and called and not self._stops(folded(before.text), named=True)

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
        """A SPEAK decision, remembered whole and sentence by sentence: on a microphone that
        hears Mochi, its own words come back as turns and must not be translated back. A piece
        that reads as a stop command ("Mochi, pode parar", in its welcome) is not remembered:
        said by a person it has to work."""
        spoken = text.rpartition("] ")[2]
        pieces = [spoken, *_SENTENCE_END.split(spoken)]
        kept = [p for p in pieces if p.strip() and not self._stops(folded(p), named=True)]
        self._own.extend(normalized(piece) for piece in [spoken, *kept])
        speak = Speak(text=text, language=language, reason=SpeakReason.ASKS_MOCHI)
        return Decision(decision=DecisionKind.SPEAK, hint=None, speak=speak, learning_events=[])

    async def _asked(self, request: InterpretRequest) -> Interpretation | None:
        try:
            return await asyncio.wait_for(self._model.interpret(request), self._timeout)
        except Exception:  # noqa: BLE001 - saying nothing is always a safe answer
            return None

    async def _in_the_other_language(self, turn: Turn, context: SessionContext) -> Decision | None:
        """The sentence in the other language, to be spoken; None when there is nothing to say
        (a filler, a model that failed)."""
        # A guess, from the small words; a short sentence with none ("Quanto custa?") goes the
        # way of the one before it. The model decides, and says which language it answered in.
        source = self._language(turn.text, self._last or context.focus)
        request = InterpretRequest(
            text=turn.text,
            recent_texts=[t.text for t in context.recent_turns[-3:]],
            source=source,
            target=other_language(source),
        )
        answer = await self._asked(request)
        sentence = _worth_saying(answer, turn.text)
        if answer is None or sentence is None:
            return None
        target = language_named(answer.language) or request.target
        self._last = other_language(target)
        # the tag puts the sentence on Mochi's screen while it is said (`device_commands`)
        return self._says(f"[translation {target.value}] {sentence}", target)
