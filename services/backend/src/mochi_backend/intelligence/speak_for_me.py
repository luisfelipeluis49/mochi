"""Speak for me (DECISIONS D-64): someone asks Mochi, by name, to speak for them. From then on
they talk in the language they are at home in, and Mochi says each sentence aloud in the
language of the meeting, until they tell it to stop.

The one case where Mochi speaks sentence after sentence without being called each time: the
person asked for exactly that, once. It needs a voice Mochi knows, because "for me" has to be
somebody: on a microphone that tells nobody apart it is refused.
"""

import asyncio
import re

from mochi_backend.intelligence.interpret_port import InterpretModel, InterpretRequest
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.settings import IntelligenceSettings
from mochi_backend.intelligence.tokens import folded, normalized
from mochi_backend.intelligence.wake_phrase import has_wake_phrase, says_mochi
from mochi_contracts import (
    Decision,
    DecisionKind,
    Language,
    Participant,
    SessionContext,
    SessionMode,
    Speak,
    SpeakReason,
    Turn,
)

# Matched on accent-folded, lower-case text: speech-to-text drops accents and capitals at will.
_ON = re.compile(
    r"\b(?:speak|talk)\s+for\s+me\b|\bfal[ae]r?\s+por\s+mim\b|\bbe\s+my\s+voice\b|\bseja\s+a\s+minha\s+voz\b"
)
# Clear without Mochi's name: nobody says these to a colleague.
_OFF_PLAIN = re.compile(
    r"\bstop\s+(?:speaking|talking)\s+for\s+me\b|\bpar[ae]r?\s+de\s+falar\s+por\s+mim\b"
)
# Only with its name: "stop" alone may be meant for a person. Short on purpose, and unlike the
# words that turn it on: in a live session "para de falar por mim" was heard as "pode falar por
# mim", which asks for the opposite (D-64).
_OFF_NAMED = re.compile(
    r"\bthat'?s\s+enough\b|\bi(?:'ll|\s+will|\s+can)\s+speak\s+(?:for\s+)?myself\b"
    r"|\bpar[ae]r?\s+de\s+falar\b|\bdeixa\s+que\s+eu\s+falo\b|\beu\s+mesm[oa]\s+falo\b"
)
# The short ones count only as the last thing said: "Mochi, pode parar" is a command, "Mochi,
# quando chega o relatório?" and "Mochi, como eu falo fila em inglês?" are questions.
_TAIL = r"(?:[\s,]+(?:now|please|thanks|thank\s+you|agora|por\s+favor|obrigad[oa]))*[\s.!?]*$"
_OFF_SHORT = re.compile(r"\b(?:stop|pode\s+parar|chega|eu\s+falo)" + _TAIL)
# With no name heard, from the person Mochi speaks for: the stop phrase and nothing else, after at
# most a greeting and one word (the name as the recogniser misheard it: "Moji, pode parar").
_OFF_ALONE = re.compile(
    r"^(?:(?:hey|hi|oi|ei|ola)[\s,]+)?(?:\w+[\s,]+)?(?:stop|pode\s+parar|chega)" + _TAIL
)
ON_LINES = {
    Language.EN: "[mood happy] Okay, I'll speak for you. To take over, say: {stop}.",
    Language.PT_BR: "[mood happy] Combinado, eu falo por você. Para voltar a falar, diga: {stop}.",
}
# The way out is taught in the language the person is at home in: said with a Brazilian accent,
# "Mochi, stop" was heard as "Mochi está" in a live session, "Mochi, pode parar" was understood.
STOP_PHRASES = {Language.EN: "Mochi, stop", Language.PT_BR: "Mochi, pode parar"}
OFF_LINES = {
    Language.EN: "Okay, over to you.",
    Language.PT_BR: "Combinado, agora é com você.",
}
NO_VOICE_LINES = {
    Language.EN: "I can only speak for someone whose voice I know. Say: Mochi, learn my voice.",
    Language.PT_BR: "Eu só falo por alguém cuja voz eu conheço. Diga: Mochi, aprende a minha voz.",
}


def _named_stop(low: str) -> bool:
    """A sentence with Mochi's name in it that tells it to stop. Example: "mochi, pode parar"."""
    return bool(_OFF_NAMED.search(low) or _OFF_SHORT.search(low))


def _says(text: str, language: Language) -> Decision:
    speak = Speak(text=text, language=language, reason=SpeakReason.ASKS_MOCHI)
    return Decision(decision=DecisionKind.SPEAK, hint=None, speak=speak, learning_events=[])


def home_of(person: Participant) -> Language:
    """The language a person is at home in. Example: Ana (pt-BR, learning en) -> pt-BR."""
    known = [lang for lang in person.comfortable_languages if lang != person.target_language]
    return known[0] if known else person.target_language


class SpeakForMe:
    """Example: `await mode.take(turn, context)` -> a SPEAK decision with the sentence said in
    the meeting's language, or None when this turn is not its business.

    One per conversation: it holds who Mochi is speaking for right now.
    """

    def __init__(
        self, model: InterpretModel, lexicon: Lexicon, settings: IntelligenceSettings
    ) -> None:
        self._model = model
        self._lexicon = lexicon
        self._enabled = settings.speak_for_me
        self._timeout = settings.model_timeout_seconds
        self._for: set[str] = set()  # user ids Mochi speaks for

    def use(self, model: InterpretModel) -> None:
        """Ask this model from now on. Example: `mode.use(OpenAiInterpretModel(chat))`."""
        self._model = model

    def fresh_session(self) -> None:
        """A session begins: Mochi speaks for nobody until asked again."""
        self._for = set()

    @property
    def speaking_for(self) -> list[str]:
        """Who Mochi speaks for now. Example: `["ana"]`."""
        return sorted(self._for)

    async def take(self, turn: Turn, context: SessionContext) -> Decision | None:
        """The decision when this turn turns the mode on or off, or is a sentence to say for
        someone; None for every other turn (the usual rules then apply)."""
        if not self._enabled or context.mode is not SessionMode.MEETING:
            return None
        low = folded(turn.text)
        named = says_mochi(turn.text) or has_wake_phrase(turn.text)
        # Off is looked for first: "para de falar por mim" holds the words that turn it on.
        if _OFF_PLAIN.search(low) or (named and _named_stop(low)):
            return self._turn_off(turn)
        if named and _ON.search(low):
            return self._turn_on(turn, context)
        person = None if named else self._whose(turn, context)  # a sentence for Mochi is not said
        if person and _OFF_ALONE.search(low):
            return self._turn_off(turn)
        return await self._said_for(person, turn, context) if person else None

    def _language(self, text: str) -> Language:
        return spoken_language(text, self._lexicon, Language.EN)

    def _turn_on(self, turn: Turn, context: SessionContext) -> Decision:
        """Speak for the person whose voice asked; nobody else can ask for them."""
        who = turn.speaker_user_id
        language = self._language(turn.text)
        if who is None or who not in {p.user_id for p in context.participants}:
            return _says(NO_VOICE_LINES[language], language)
        self._for.add(who)
        person = next(p for p in context.participants if p.user_id == who)
        return _says(ON_LINES[language].format(stop=STOP_PHRASES[home_of(person)]), language)

    def _turn_off(self, turn: Turn) -> Decision | None:
        """Stop for the person who asked. Any other voice (one Mochi could not name, or one it took
        for a colleague: the device gets the speaker wrong now and then) stops it for everyone:
        better silent than speaking for someone who wants to speak. None when it was off."""
        who = turn.speaker_user_id
        if not self._for:
            return None
        self._for = self._for - {who} if who in self._for else set()
        language = self._language(turn.text)
        return _says(OFF_LINES[language], language)

    def _whose(self, turn: Turn, context: SessionContext) -> Participant | None:
        """The person this sentence is said for: the recognised speaker when Mochi speaks for
        them; or, when the voice was not recognised and Mochi speaks for exactly one person, that
        person (the sentence must then be in their language, see `_said_for`)."""
        people = {p.user_id: p for p in context.participants}
        who = turn.speaker_user_id
        if who is not None:
            return people.get(who) if who in self._for else None
        only = next(iter(self._for)) if len(self._for) == 1 else None
        return people.get(only) if only else None

    async def _said_for(
        self, person: Participant, turn: Turn, context: SessionContext
    ) -> Decision | None:
        """Their sentence in the language they are learning (the meeting's), to be spoken; None
        when they said it in that language themselves, or nothing can be said for them."""
        source, target = home_of(person), person.target_language
        if source is target or spoken_language(turn.text, self._lexicon, source) is target:
            return None
        request = InterpretRequest(
            text=turn.text,
            recent_texts=[t.text for t in context.recent_turns[-3:]],
            source=source,
            target=target,
        )
        try:
            answer = await asyncio.wait_for(self._model.interpret(request), self._timeout)
        except Exception:  # noqa: BLE001 - saying nothing is always a safe answer
            return None
        sentence = " ".join((answer.sentence or "").split()) if answer else ""
        if answer is None or answer.decision != "SAY" or not sentence:
            return None
        if normalized(sentence) == normalized(turn.text):
            return None  # the same words back: there is nothing to say for them
        return _says(sentence, target)
