"""What a team gets wrong and what was explained to it: numbers only (DECISIONS D-53, D-54)."""

from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS, DEMO_USERS
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.storage.factory import TeamStart
from mochi_backend.team.facts import TeamFacts
from mochi_backend.team.journal import SessionJournal
from mochi_backend.team.ledger import TeamLedger
from mochi_backend.team.speech import explained_in, mistakes_in
from mochi_backend.team.team_view import team_insights
from mochi_contracts import (
    ConversationReport,
    HintCandidate,
    MarkKind,
    Mistake,
    MistakeKind,
    MistakeTopic,
    SessionMode,
    TranscriptMark,
    Utterance,
)
from tests.factories import make_hint, make_turn
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_storage import FakeStorage
from tests.unit.test_speech_report import draft
from tests.unit.test_team_view import NOW, at


def report(user: str, days_ago: float = 1.0, **counts: int) -> ConversationReport:
    """One person's report with `counts` mistakes per topic, e.g. `verb_tense=5`."""
    mistakes = [
        Mistake(
            kind=MistakeKind.GRAMMAR,
            topic=MistakeTopic(topic),
            said="private sentence",
            better="private sentence, right",
            explanation=None,
            count=count,
        )
        for topic, count in counts.items()
    ]
    changed = {"report_id": f"rep_{user}_{days_ago}", "user_id": user, "mistakes": mistakes}
    return draft().model_copy(update={**changed, "ended_at": at(days_ago)})


def said(text: str, days_ago: float, *marks: TranscriptMark) -> Utterance:
    return Utterance(
        utterance_id=f"seg_{text}_{days_ago}",
        company_id="demo",
        record_id="rec_1",
        user_id=None,
        text=text,
        at=at(days_ago),
        marks=list(marks),
    )


IDIOM = TranscriptMark(kind=MarkKind.IDIOM, text="circle back", gloss="voltar ao assunto")
TERM = TranscriptMark(kind=MarkKind.TECHNICAL_TERM, text="Churn rate", gloss="cancelamentos")
SWITCH = TranscriptMark(kind=MarkKind.CODE_SWITCH, text="adiar", gloss="postpone")


def test_a_mistake_counts_only_when_at_least_three_people_share_it() -> None:
    reports = [
        report("ana", verb_tense=5, articles=2),
        report("ben", verb_tense=2, articles=1),
        report("caio", verb_tense=1),
        report("ana", days_ago=2, verb_tense=1),
    ]
    [shared] = mistakes_in(reports)
    assert (shared.topic, shared.kind, shared.people, shared.times) == (
        "verb_tense",
        "grammar",
        3,
        9,
    )
    assert mistakes_in(reports, min_people=4) == []
    assert mistakes_in([report("ana", verb_tense=9)]) == []  # it would point at her
    # ... and what two people share points at the other one, for whichever of them is looking
    assert mistakes_in([report("ana", verb_tense=9), report("ben", verb_tense=1)]) == []


def test_explained_terms_are_counted_without_who_said_them() -> None:
    sentences = [
        said("a", 1, IDIOM),
        said("b", 2, IDIOM, SWITCH),
        said("c", 3, TERM),
        said("d", 4),
    ]
    idiom, term = explained_in(sentences)
    assert (idiom.expression, idiom.times, idiom.last_at) == ("circle back", 2, at(1))
    assert (term.expression, term.kind, term.meaning) == (
        "Churn rate",
        "technical_term",
        "cancelamentos",
    )


def test_the_team_view_carries_both_for_its_period_and_no_sentence() -> None:
    users = {user.user_id: user for user in DEMO_USERS}
    facts = TeamFacts(
        DEMO_COMPANY,
        DEMO_MEMBERS,
        users,
        reports=[
            report("ana", verb_tense=1),
            report("ben", verb_tense=1),
            report("caio", verb_tense=1),
            report("ben", 90, plurals=4),
        ],
        said=[said("recent", 1, IDIOM), said("long ago", 90, TERM)],
    )
    view = team_insights(facts, NOW, period_days=30)
    assert [(m.topic, m.people) for m in view.mistakes] == [("verb_tense", 3)]
    assert [t.expression for t in view.explained] == ["circle back"]
    assert "private sentence" not in view.model_dump_json()


def test_the_journal_keeps_what_was_noticed_and_hands_back_the_closed_record() -> None:
    storage, clock = FakeStorage(), FakeClock()
    ledger = TeamLedger(storage, TeamStart(), DEMO_COMPANY, DEMO_MEMBERS)
    journal = SessionJournal(ledger, clock, SequentialIdGenerator(), "demo")
    assert journal.end() is None and journal.noticed("seg_0", IDIOM) is None
    journal.begin("demo", SessionMode.MEETING, ["ana", "ben"])
    turn = make_turn("Let's circle back on that")
    journal.heard(turn, [SWITCH])
    stopped_at = make_hint(0).model_copy(
        update={"candidates": [HintCandidate(expression="Raincoat", meaning=None)]}
    )
    journal.needed(stopped_at, turn)
    assert journal.words_shown() == ["postpone", "raincoat"]  # the other words on the card too
    marked = journal.noticed(turn.segment_id, IDIOM)
    assert marked is not None and marked.marks == [SWITCH, IDIOM]
    assert journal.noticed("seg_unknown", IDIOM) is None
    closed = journal.end()
    assert closed is not None and closed.ended_at is not None
    assert ledger.record(closed.record_id) == closed and ledger.utterance(turn.segment_id) == marked
    assert ledger.utterances_of("demo") == [marked] and ledger.utterances_of("other") == []
    assert journal.noticed(turn.segment_id, TERM) is None  # the session is over
    kept = report("ana", verb_tense=1)
    ledger.keep_report(kept)
    assert ledger.reports_by("ana") == [kept] and ledger.reports_of("demo") == [kept]
    assert ledger.reports_by("ben") == []
    ledger.clear_history()
    assert ledger.reports_of("demo") == [] and ledger.record(closed.record_id) is None
