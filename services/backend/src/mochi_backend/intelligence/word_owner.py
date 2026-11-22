"""Whose word is it (AGENTS 7.3)."""

from mochi_contracts import SessionContext, SessionMode


def owner_for(context: SessionContext, speaker: str | None = None) -> str | None:
    """Whose word it is: the recognised speaker when they are learning the spoken (focus)
    language, else the one participant learning it, else None.

    A meeting has more than two people, and several may be learning the same language: then
    only the voice tells whose sentence it was (`Turn.speaker_user_id`, DECISIONS D-44). The
    device reports a voice when it changes, so the name can be a moment stale: a speaker who is
    not learning this language is not believed, and the old rule decides.
    In a review there is one person, and every word is theirs, whichever language they ask in.
    Example: with focus "en", Ana (target "en") and Ben (target "pt-BR") -> "ana", also when
    the device still says "ben".
    """
    if context.mode is SessionMode.REVIEW and context.participants:
        return context.participants[0].user_id
    learners = [p.user_id for p in context.participants if p.target_language == context.focus]
    if speaker in learners:
        return speaker
    return learners[0] if len(learners) == 1 else None
