"""What was wrong in what one person said, written into their report (DECISIONS D-54)."""

from mochi_backend.intelligence.coach_port import (
    CoachAnswer,
    CoachRequest,
    Correction,
    NullCoachModel,
)
from mochi_backend.intelligence.json_chat import JsonChat, JsonChatConfig
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.openai_coach_model import OpenAiCoachModel, parse_coach_answer
from mochi_backend.intelligence.speech_report import (
    MAX_SENTENCES,
    completed,
    home_language,
    in_target_language,
    with_answer,
)
from mochi_contracts import (
    ConversationReport,
    Language,
    MistakeKind,
    MistakeTopic,
    SessionMode,
    SpokenSentence,
)
from tests.factories import ANA, BEN
from tests.fakes.fake_coach_model import FakeCoachModel
from tests.fakes.fake_http_client import FakeHttpClient
from tests.unit.test_explaining import _reply

AT = "2026-11-19T16:00:04.500Z"
SAID = [
    "I finish the slides yesterday.",
    "Can we talk about the budget?",
    "She don't have the numbers.",
    "I send the report yesterday.",
    "Você pode me passar o relatório, por favor?",
]


def draft(sentences: list[str] | None = None) -> ConversationReport:
    """Ana's report of one meeting before anybody looked at her sentences."""
    said = SAID if sentences is None else sentences
    return ConversationReport(
        report_id="rep_1",
        company_id="demo",
        record_id="rec_1",
        user_id="ana",
        target_language=Language.EN,
        mode=SessionMode.MEETING,
        started_at=AT,
        ended_at=AT,
        speaking_minutes=0.2,
        my_sentences=[
            SpokenSentence(utterance_id=f"seg_{n}", at=AT, text=text) for n, text in enumerate(said)
        ],
        mistakes=[],
        unknown_words=[],
        strengths=[],
        focus_next=[],
    )


def fix(index: int, better: str, topic: str = "verb_tense", kind: str = "grammar") -> Correction:
    return Correction(index=index, better=better, kind=kind, topic=topic, explanation="Porque sim.")


ANSWER = CoachAnswer(
    corrections=[
        fix(0, "I finished the slides yesterday."),
        fix(2, "She doesn't have the numbers.", "agreement"),
        fix(3, "I sent the report yesterday."),
    ],
    strengths=[" Você pergunta com clareza. ", "", "Bom vocabulário.", "Um a mais."],
    focus_next=["Passado: finished, sent."],
)


def test_corrections_land_on_their_sentences_and_mistakes_are_grouped_by_kind() -> None:
    report = with_answer(draft(), ANSWER)
    better = [(s.better, s.topic) for s in report.my_sentences]
    assert better[0] == ("I finished the slides yesterday.", MistakeTopic.VERB_TENSE)
    assert better[1] == (None, None) and better[2][1] is MistakeTopic.AGREEMENT
    tense, agreement = report.mistakes
    assert (tense.kind, tense.topic, tense.count) == (MistakeKind.GRAMMAR, "verb_tense", 2)
    assert (tense.said, tense.better) == (SAID[0], "I finished the slides yesterday.")
    assert tense.explanation == "Porque sim." and agreement.count == 1
    assert report.strengths == ["Você pergunta com clareza.", "Bom vocabulário."]
    assert report.focus_next == ["Passado: finished, sent."]


def test_a_correction_that_does_not_hold_up_is_left_out() -> None:
    doubtful = CoachAnswer(
        corrections=[
            fix(9, "No such sentence."),
            fix(1, "Can we talk about the budget"),  # only the question mark changed
            fix(0, "I finished the slides yesterday.", kind="spelling"),  # not a kind we know
            fix(2, "She doesn't have the numbers.", topic="conjugation"),  # unknown group
            fix(3, "  "),
        ]
    )
    report = with_answer(draft(), doubtful)
    [only] = report.mistakes
    assert (only.topic, only.said) == (MistakeTopic.OTHER, SAID[2])
    assert [s.better for s in report.my_sentences].count(None) == len(SAID) - 1


def test_a_sentence_in_the_persons_own_language_is_never_a_mistake() -> None:
    answer = CoachAnswer(corrections=[fix(4, "Can you pass me the report, please?"), fix(0, "x")])
    kept = in_target_language(answer, draft(), Lexicon.load())
    assert [c.index for c in kept.corrections] == [0]


async def test_the_coach_is_asked_in_the_persons_languages_and_no_answer_means_no_report() -> None:
    coach = FakeCoachModel(ANSWER)
    report = await completed(coach, draft(), ANA, Lexicon.load())
    assert report is not None and len(report.mistakes) == 2
    [asked] = coach.requests
    assert (asked.target_language, asked.home_language) == (Language.EN, Language.PT_BR)
    assert asked.sentences == SAID
    assert await completed(FakeCoachModel(None), draft(), ANA, Lexicon.load()) is None
    assert await completed(NullCoachModel(), draft(), ANA, Lexicon.load()) is None
    long = FakeCoachModel(CoachAnswer())
    await completed(long, draft(["I agree with that."] * (MAX_SENTENCES + 20)), ANA, Lexicon.load())
    assert len(long.requests[0].sentences) == MAX_SENTENCES
    assert home_language(BEN) is Language.EN
    same = BEN.model_copy(update={"comfortable_languages": [Language.PT_BR]})
    assert home_language(same) is Language.PT_BR  # nothing else is known: their target


async def test_the_openai_coach_numbers_the_sentences_and_reads_the_json() -> None:
    answer = '{"corrections": [{"index": 0, "better": "I finished it.", "kind": "grammar", '
    answer += (
        '"topic": "verb_tense", "explanation": "Passado."}], "strengths": [], "focus_next": []}'
    )
    http = FakeHttpClient([_reply(answer), _reply('{"corrections": "none"}')])
    config = JsonChatConfig("https://llm.example/v1", "tiny", "k", 60.0)
    model = OpenAiCoachModel(JsonChat(http, config, "coach"))
    request = CoachRequest(
        sentences=["I finish it."], target_language=Language.EN, home_language=Language.PT_BR
    )
    found = await model.review(request)
    assert found is not None and found.corrections[0].better == "I finished it."
    sent = http.posts[0].payload
    assert isinstance(sent, dict) and isinstance(sent["messages"], list)
    assert '"index": 0' in str(sent["messages"][-1]) and http.posts[0].timeout_seconds == 60.0
    assert await model.review(request) is None  # not the shape that was asked for
    assert parse_coach_answer("{}") == CoachAnswer()
