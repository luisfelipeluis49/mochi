"""Whose word is it (AGENTS 7.3)."""

from mochi_contracts import SessionContext


def owner_for(context: SessionContext) -> str | None:
    """The one participant learning the spoken (focus) language, else None.

    Example: with focus "en", Ana (target "en") and Ben (target "pt-BR") -> "ana".
    """
    learners = [p.user_id for p in context.participants if p.target_language == context.focus]
    return learners[0] if len(learners) == 1 else None
