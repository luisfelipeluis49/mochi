"""What a training is built from: one person's earlier conversations, read from the database (D-68).

Training is a role-play that resembles the moments where a person needed a word or made a mistake,
so Mochi is handed those moments, one short line each. They are that person's own (their words,
their sentences) and go only to the model that plays the scene, never to anyone's screen.
"""

from mochi_backend.team.ledger import TeamLedger
from mochi_contracts import ConversationReport, WordMoment

MOMENTS_KEPT = 6  # the newest word moments
REPORTS_KEPT = 3  # the newest conversation reports


def _moment_line(moment: WordMoment) -> str:
    said = f' when they said "{moment.heard}"' if moment.heard else ""
    return f"needed the word {moment.expression} ({moment.meaning or 'no translation'}){said}"


def _report_lines(report: ConversationReport) -> list[str]:
    mistakes = [
        f'said "{m.said}" instead of "{m.better}" ({m.topic.value})' for m in report.mistakes
    ]
    return [*mistakes, *(f"to work on: {line}" for line in report.focus_next)]


class PracticeBrief:
    """Example: `PracticeBrief(ledger).for_user("ana")[0]` is `'needed the word postpone (adiar)
    when they said "I need to adiar my meeting"'`."""

    def __init__(self, ledger: TeamLedger) -> None:
        self._ledger = ledger

    def for_user(self, user_id: str) -> list[str]:
        """Lines about this person's moments and mistakes, newest first; empty with no history."""
        moments = [
            m
            for company in self._ledger.companies_of(user_id)
            for m in self._ledger.moments_of(company)
            if m.user_id == user_id
        ]
        newest = list(reversed(moments))[:MOMENTS_KEPT]
        reports = list(reversed(self._ledger.reports_by(user_id)))[:REPORTS_KEPT]
        return [*map(_moment_line, newest), *(line for r in reports for line in _report_lines(r))]
