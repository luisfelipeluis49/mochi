"""The meeting beyond the stuck word: a live transcript, a code switch everyone sees, idioms
explained, and afterwards a private report and "used on your own" (DECISIONS D-51 to D-55)."""

import json

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.intelligence.coach_port import CoachAnswer, Correction
from mochi_contracts import (
    ConversationReport,
    LearningEvent,
    LearningState,
    MarkKind,
    MistakeTopic,
    SessionMode,
    TranscriptLine,
)
from tests.fakes.fake_coach_model import FakeCoachModel
from tests.fakes.fake_explain_model import FakeExplainModel, GatedExplainModel
from tests.fakes.fake_sender import FakeSender
from tests.fakes.fake_storage import FakeStorage
from tests.harness import ANA, ANA_AR, AUDIENCE, BEN, HOME, Harness, make_harness
from tests.unit.test_team_view import card

ADIAR = "I need to adiar my meeting tomorrow."
CIRCLE = "Let's circle back on pricing after the launch."
LIVE = {"MOCHI_LIVE_TRANSCRIPT": "true", "MOCHI_ENABLE_DEV_ROUTES": "true"}
COACHED = CoachAnswer(
    corrections=[
        Correction(
            index=1,
            better="I finished the slides yesterday.",
            kind="grammar",
            topic="verb_tense",
            explanation="Com yesterday, use finished.",
        )
    ],
    strengths=["Você explica bem."],
    focus_next=["Passado: finished."],
)


async def _meeting(**fakes: object) -> Harness:
    harness = make_harness(env=LIVE, **fakes)  # type: ignore[arg-type]
    await harness.container.sessions.start()
    return harness


def _lines(sender: FakeSender) -> list[TranscriptLine]:
    return [e.payload for e in sender.events if isinstance(e.payload, TranscriptLine)]


def _reports(sender: FakeSender) -> list[ConversationReport]:
    return [e.payload for e in sender.events if isinstance(e.payload, ConversationReport)]


async def _says(harness: Harness, who: str | None, text: str) -> None:
    harness.container.core.store.speaker = who  # the voice the device recognised
    await harness.say(text)
    await harness.container.pipeline.settle()


async def test_every_sentence_reaches_every_screen_of_the_session_as_it_is_said() -> None:
    harness = await _meeting()
    ana, ben, home, audience, glasses = await harness.connect_all(ANA, BEN, HOME, AUDIENCE, ANA_AR)
    await _says(harness, "ben", "Shall we start with the budget?")
    for screen in (ana, ben, home, audience):
        [line] = _lines(screen)
        assert (line.user_id, line.text, line.marks) == (
            "ben",
            "Shall we start with the budget?",
            [],
        )
    assert _lines(glasses) == []  # glasses show the wearer's hints and nothing else
    [caption] = harness.container.core.store.commands
    assert caption.kind == "caption"
    assert json.loads(caption.value) == {"who": "Ben", "text": "Shall we start with the budget?"}


async def test_nothing_is_shown_with_the_transcript_switched_off_or_after_stop() -> None:
    off = make_harness()
    await off.container.sessions.start()
    [ben] = await off.connect_all(BEN)
    await off.say(ADIAR)
    assert _lines(ben) == [] and [c.kind for c in off.container.core.store.commands] == ["hint"]
    on = await _meeting()
    [ana] = await on.connect_all(ANA)
    await on.container.sessions.stop()
    await on.say("Is anybody still here?")
    assert _lines(ana) == []


async def test_a_code_switch_is_marked_for_everyone_and_the_hint_stays_the_speakers() -> None:
    harness = await _meeting()
    ana, ben = await harness.connect_all(ANA, BEN)
    await _says(harness, "ana", ADIAR)
    [seen] = _lines(ben)
    [mark] = seen.marks
    assert (mark.kind, mark.text, mark.gloss) == (MarkKind.CODE_SWITCH, "adiar", "postpone")
    assert "hint.created" in ana.types() and "hint.created" not in ben.types()
    kinds = {c.kind: json.loads(c.value) for c in harness.container.core.store.commands}
    assert kinds["hint"]["why"] == "code_switch" and kinds["caption"]["who"] == "Ana"
    [kept] = harness.container.core.journal.transcript()
    assert kept.marks == seen.marks  # the person's own page shows it with the sentence


async def test_an_idiom_is_explained_a_moment_later_on_the_same_line() -> None:
    explains = FakeExplainModel({"circle back": "voltar ao assunto depois"})
    harness = await _meeting(explains=explains)
    [ana] = await harness.connect_all(ANA)
    await _says(harness, "ben", CIRCLE)
    first, again = _lines(ana)
    assert first.utterance_id == again.utterance_id and first.marks == []
    [mark] = again.marks
    assert (mark.kind, mark.text, mark.gloss) == (
        MarkKind.IDIOM,
        "circle back",
        "voltar ao assunto depois",
    )
    assert "hint.created" not in ana.types()  # an explanation is no hint: no word is saved
    assert harness.container.core.intelligence.words_for("ana") == []
    kinds = [c.kind for c in harness.container.core.store.commands]
    assert kinds == ["caption", "explain"]  # one caption: the line was only marked again
    card_shown = json.loads(harness.container.core.store.commands[-1].value)
    assert card_shown["word"] == "circle back" and card_shown["kind"] == "idiom"
    assert "explained" in harness.logger.names()
    client = TestClient(create_app(harness.container))
    insights = client.get("/api/companies/demo/insights", params={"viewer": "ana"}).json()
    assert [(t["expression"], t["times"]) for t in insights["explained"]] == [("circle back", 1)]


async def test_an_explanation_is_marked_but_never_covers_a_hint_on_mochis_screen() -> None:
    harness = await _meeting(explains=FakeExplainModel({"circle back": "voltar ao assunto"}))
    [ana] = await harness.connect_all(ANA)
    await _says(harness, "ana", ADIAR)  # her hint is on the screen for eight seconds
    await _says(harness, "ben", CIRCLE)  # a second later
    assert [m.text for m in _lines(ana)[-1].marks] == ["circle back"]
    kinds = [c.kind for c in harness.container.core.store.commands]
    assert "hint" in kinds and "explain" not in kinds


async def test_a_stuck_speaker_is_never_asked_about_idioms_and_a_stopped_session_shows_none() -> (
    None
):
    explains = FakeExplainModel({"circle back": "voltar", "adiar": "x"})
    harness = await _meeting(explains=explains)
    await _says(harness, "ana", ADIAR)  # a hint was shown: the explainer is not even asked
    assert explains.requests == []
    harness.clock.advance(30)
    harness.container.core.store.speaker = "ben"
    await harness.say(CIRCLE)
    await harness.container.sessions.stop()  # before the explanation arrived
    await harness.container.pipeline.settle()
    assert "explain" not in [c.kind for c in harness.container.core.store.commands]
    assert "explained" not in harness.logger.names()


async def test_after_stop_each_person_gets_a_private_report_of_what_they_said() -> None:
    coach, storage = FakeCoachModel(COACHED), FakeStorage()
    harness = await _meeting(coach=coach, storage=storage)
    ana, ben, home = await harness.connect_all(ANA, BEN, HOME)
    await _says(harness, "ana", ADIAR)
    await _says(harness, "ana", "I finish the slides yesterday.")
    await _says(harness, "ben", "Great, thank you for that.")
    await _says(harness, "ana", "We can talk about the budget now.")
    await harness.container.sessions.stop()
    assert _reports(ana) == []  # written in the background: Stop did not wait
    assert await harness.scheduler.run_due() == 1
    [report] = _reports(ana)
    assert _reports(ben) == [] and _reports(home) == []
    assert [s.text for s in report.my_sentences] == [
        ADIAR,
        "I finish the slides yesterday.",
        "We can talk about the budget now.",
    ]
    assert report.my_sentences[1].better == "I finished the slides yesterday."
    [mistake] = report.mistakes
    assert (mistake.topic, mistake.count) == (MistakeTopic.VERB_TENSE, 1)
    [needed] = report.unknown_words
    assert (needed.expression, needed.said_instead, needed.times) == ("postpone", ADIAR, 1)
    assert report.mode.value == "meeting" and report.speaking_minutes > 0
    assert len(coach.requests) == 1  # Ben said one sentence: too little to judge
    assert list(storage.reports) == [report.report_id]
    client = TestClient(create_app(harness.container))
    mine = client.get("/api/users/ana/reports", params={"viewer": "ana"})
    assert mine.status_code == 200 and mine.json()[0]["report_id"] == report.report_id
    assert client.get("/api/users/ana/reports", params={"viewer": "ben"}).status_code == 403
    insights = client.get("/api/companies/demo/insights", params={"viewer": "ana"}).json()
    assert insights["mistakes"] == []  # one person's mistake would point at that person
    [later] = await harness.connect_all(ANA)  # a phone opened afterwards still gets it
    assert [r.report_id for r in _reports(later)] == [report.report_id]
    await harness.container.demo_reset.run()
    assert client.get("/api/users/ana/reports", params={"viewer": "ana"}).json() == []


async def test_a_review_is_shown_to_nobody_else_and_another_voices_sentence_stays_out() -> None:
    review = make_harness(env=LIVE)
    await review.container.sessions.start(mode=SessionMode.REVIEW, user_id="ana")
    ana, ben, audience = await review.connect_all(ANA, BEN, AUDIENCE)
    await review.say("I think the word is umbrella, right?")
    assert [_lines(screen) for screen in (ana, ben, audience)] == [[], [], []]
    assert "caption" not in [c.kind for c in review.container.core.store.commands]
    meeting = await _meeting(coach=FakeCoachModel(COACHED))
    await _says(meeting, "ben", ADIAR)  # Ben's voice; the word is Ana's all the same (7.3)
    for _ in range(3):
        await _says(meeting, "ana", "I finish the slides yesterday.")
    await meeting.container.sessions.stop()
    await meeting.scheduler.run_due()
    [report] = meeting.container.team_service.reports_of("ana", "ana")
    [needed] = report.unknown_words
    assert (needed.expression, needed.said_instead) == ("postpone", None)
    assert ADIAR not in report.model_dump_json()


async def test_a_word_read_off_a_card_is_not_used_on_your_own() -> None:
    harness = make_harness()
    brain = harness.container.core.intelligence
    brain.apply([card("postpone", "ana", days_ago=3)])
    await harness.container.sessions.start()
    await _says(harness, "ana", ADIAR)  # "postpone" is on the screen
    harness.clock.advance(600)
    await _says(harness, "ana", "So we will postpone it, I think.")
    await harness.container.sessions.stop()
    await harness.scheduler.run_due()
    [kept] = brain.words_for("ana")
    assert kept.learning_state is not LearningState.USED_INDEPENDENTLY


async def test_an_explanation_for_a_session_that_ended_never_lands_in_the_next() -> None:
    explains = GatedExplainModel({"circle back": "voltar"})
    harness = await _meeting(explains=explains)
    harness.container.core.store.speaker = "ben"
    await harness.say(CIRCLE)
    await harness.container.sessions.stop()
    await harness.container.sessions.start()  # a new session before the model answered
    [ana] = await harness.connect_all(ANA)
    explains.gate.set()
    await harness.container.pipeline.settle()
    assert _lines(ana) == [] and "explained" not in harness.logger.names()
    assert "explain" not in [c.kind for c in harness.container.core.store.commands]


async def test_no_report_without_a_coach_or_when_reports_are_off_or_history_was_reset() -> None:
    silent = await _meeting()
    for _ in range(3):
        await _says(silent, "ana", "I finish the slides yesterday.")
    await silent.container.sessions.stop()
    await silent.scheduler.run_due()
    assert silent.container.team_service.reports_of("ana", "ana") == []
    off = make_harness(
        env={"MOCHI_SPEECH_REPORTS": "false"}, coach=(unused := FakeCoachModel(COACHED))
    )
    await off.container.sessions.start()
    for _ in range(3):
        await _says(off, "ana", "I finish the slides yesterday.")
    await off.container.sessions.stop()
    await off.scheduler.run_due()
    assert unused.requests == []
    wiped = await _meeting(coach=FakeCoachModel(COACHED))
    for _ in range(3):
        await _says(wiped, "ana", "I finish the slides yesterday.")
    await wiped.container.sessions.stop()
    await wiped.container.demo_reset.run()
    await wiped.scheduler.run_due()
    assert wiped.container.team_service.reports_of("ana", "ana") == []
    assert "report_failed" not in wiped.logger.names()


async def test_a_saved_word_said_with_no_hint_in_a_later_meeting_is_used_on_your_own() -> None:
    harness = make_harness()
    brain = harness.container.core.intelligence
    brain.apply([card("postpone", "ana", days_ago=3), card("umbrella", "ana", days_ago=3)])
    await harness.container.sessions.start()
    [ana] = await harness.connect_all(ANA)
    await _says(harness, "ben", "Did you bring an umbrella today?")
    await _says(harness, "ana", "No, I forgot my umbrella at home.")  # she repeats his word
    await _says(harness, "ana", "By the way, we should postpone the review.")
    before = len(ana.events)
    await harness.container.sessions.stop()
    await harness.scheduler.run_due()
    states = {w.expression: w.learning_state for w in brain.words_for("ana")}
    assert states == {
        "postpone": LearningState.USED_INDEPENDENTLY,
        "umbrella": LearningState.DISCOVERED,
    }
    updates = [e.payload for e in ana.events[before:] if isinstance(e.payload, LearningEvent)]
    assert [(u.expression, len(u.state_history)) for u in updates] == [("postpone", 2)]
    client = TestClient(create_app(harness.container))
    funnel = client.get("/api/companies/demo/insights", params={"viewer": "ana"}).json()["funnel"]
    assert funnel["used_independently"] == 1
