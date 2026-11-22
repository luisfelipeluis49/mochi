"""What Mochi is told in a training: a role-play built from the person's own meetings (D-68).

Training replaces the word-by-word review. Mochi plays a colleague in a NEW situation like the ones
where this person needed a word or made a mistake, steers it so the words they need come up
naturally, never helps, and after about five minutes gives kind feedback.
"""

from mochi_backend.intelligence.character_port import CharacterRequest

TRAINING_MINUTES = 5.0  # what the person is told: "about five minutes"
WRAP_UP_AT = 4.0  # from here Mochi stops opening new topics and gives its feedback

TRAINING_NOTE = (
    "This session is a TRAINING with one person, on their phone. You play a colleague or client in "
    "a short work role-play, in the language they are learning, in 1 to 3 short sentences at a "
    "time. Invent a NEW situation: the history below shows the kind of moment where they needed a "
    "word or made a mistake, but never use the same people, place, topic or sentences. Steer the "
    "scene so the words they need come up naturally. Target words (the word, what it means in "
    "their own language, whether they already used it): {words}. {mistakes}"
    "Rules: you never say a target word before they do, and you give no hint, clue, translation, "
    "spelling or correction while the role-play runs. If they miss a word, carry on; "
    "do not ask for it again. Never mention that this is a test."
)
HISTORY_NOTE = (
    "Moments from their earlier conversations (inspiration only, never repeat): {lines}. "
)
NO_HISTORY_NOTE = "They have no history yet: invent an everyday work situation. "
CLOCK_NOTE = "About {minute:.1f} of {total:.0f} minutes have passed."
WRAP_UP_NOTE = (
    "Time is nearly up: finish the scene in one sentence and give your feedback now, then say "
    "goodbye with [mood proud][bye]. The feedback is warm and positive: start with what went well "
    "and where they are improving (compare with the history: a word they used on their own, a "
    "mistake from before that they did not make today). For each target word they did not use, "
    "give it its own short sentence in the language they are learning, using it in a way that "
    "fits what they were doing, as something to try next time, never as a failure. Name at most "
    "one thing to improve. Keep it short, in simple words."
)


def _words(request: CharacterRequest) -> str:
    return "; ".join(
        f"{w.expression} ({w.meaning or 'no translation'}, {'used' if w.used else 'not used yet'})"
        for w in request.review
    )


def training_note(request: CharacterRequest) -> str:
    """The note that tells Mochi it is in a training, with the clock.

    Example: a request with the target "postpone" three minutes in has "postpone (adiar, not
    used yet)" and "About 3.0 of 5 minutes have passed."
    """
    seen = HISTORY_NOTE.format(lines=" | ".join(request.practice))
    note = TRAINING_NOTE.format(
        words=_words(request), mistakes=seen if request.practice else NO_HISTORY_NOTE
    )
    note += " " + CLOCK_NOTE.format(minute=request.minute, total=TRAINING_MINUTES)
    return note + (" " + WRAP_UP_NOTE if request.minute >= WRAP_UP_AT else "")
