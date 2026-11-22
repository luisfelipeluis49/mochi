"""What was wrong in what one person said: the coach model's answer written into their report.

Nothing of this is shown in the meeting. It is for that person's own page afterwards (D-54).
"""

from collections import Counter

from mochi_backend.intelligence.coach_port import CoachAnswer, CoachModel, CoachRequest, Correction
from mochi_backend.intelligence.language_guess import spoken_language
from mochi_backend.intelligence.lexicon import Lexicon
from mochi_backend.intelligence.tokens import normalized
from mochi_contracts import (
    ConversationReport,
    Language,
    Mistake,
    MistakeKind,
    MistakeTopic,
    Participant,
    SpokenSentence,
)

MAX_STRENGTHS = 2
MAX_FOCUS = 3
MAX_SENTENCES = 150  # what one call looks at: an hour of meeting is more, and a prompt has an end
_TOPICS = {topic.value: topic for topic in MistakeTopic}
_KINDS = {kind.value: kind for kind in MistakeKind}


def home_language(person: Participant) -> Language:
    """The language to write to this person in: the first one they are at home in.

    Example: Ana (comfortable in pt-BR, learning en) -> pt-BR.
    """
    known = [lang for lang in person.comfortable_languages if lang != person.target_language]
    return known[0] if known else person.target_language


def _real(correction: Correction, sentences: list[SpokenSentence]) -> bool:
    """A correction of a sentence that exists, that changes its words, of a kind we know."""
    if not 0 <= correction.index < len(sentences) or correction.kind not in _KINDS:
        return False
    better = normalized(correction.better)
    return bool(better) and better != normalized(sentences[correction.index].text)


def _topic(correction: Correction) -> MistakeTopic:
    return _TOPICS.get(correction.topic or "", MistakeTopic.OTHER)


def _marked(sentences: list[SpokenSentence], kept: dict[int, Correction]) -> list[SpokenSentence]:
    """Each sentence, with its correction when it has one."""
    return [
        sentence.model_copy(
            update={"better": kept[index].better.strip(), "topic": _topic(kept[index])}
        )
        if index in kept
        else sentence
        for index, sentence in enumerate(sentences)
    ]


def _mistakes(sentences: list[SpokenSentence], kept: dict[int, Correction]) -> list[Mistake]:
    """One entry per kind and topic: its first example, and how often it came up."""
    groups = Counter((_KINDS[c.kind or ""], _topic(c)) for c in kept.values())
    first: dict[tuple[MistakeKind, MistakeTopic], int] = {}
    for index in sorted(kept):
        first.setdefault((_KINDS[kept[index].kind or ""], _topic(kept[index])), index)
    return [
        Mistake(
            kind=kind,
            topic=topic,
            said=sentences[first[(kind, topic)]].text,
            better=kept[first[(kind, topic)]].better.strip(),
            explanation=(kept[first[(kind, topic)]].explanation or "").strip() or None,
            count=count,
        )
        for (kind, topic), count in groups.most_common()
    ]


def _lines(given: list[str], limit: int) -> list[str]:
    return [line.strip() for line in given if line.strip()][:limit]


def with_answer(draft: ConversationReport, answer: CoachAnswer) -> ConversationReport:
    """The draft with the coach's answer in it; what does not hold up is left out.

    Example: a correction for sentence 7 of a five-sentence report is dropped.
    """
    sentences = draft.my_sentences
    kept = {c.index: c for c in reversed(answer.corrections) if _real(c, sentences)}
    return draft.model_copy(
        update={
            "my_sentences": _marked(sentences, kept),
            "mistakes": _mistakes(sentences, kept),
            "strengths": _lines(answer.strengths, MAX_STRENGTHS),
            "focus_next": _lines(answer.focus_next, MAX_FOCUS),
        }
    )


def in_target_language(
    answer: CoachAnswer, draft: ConversationReport, lexicon: Lexicon
) -> CoachAnswer:
    """The answer without corrections of sentences said in the person's own language: someone
    who turns to a colleague in Portuguese has made no mistake in English.

    Example: a "correction" of "Você pode me passar o relatório?" for a learner of English goes.
    """
    target, sentences = draft.target_language, draft.my_sentences
    kept = [
        c
        for c in answer.corrections
        if 0 <= c.index < len(sentences)
        and spoken_language(sentences[c.index].text, lexicon, target) is target
    ]
    return answer.model_copy(update={"corrections": kept})


async def completed(
    coach: CoachModel, draft: ConversationReport, person: Participant, lexicon: Lexicon
) -> ConversationReport | None:
    """Ask the coach about the draft's sentences and write its answer in.

    None without an answer: "nothing was wrong" must not be said for "nobody looked".
    Example: `await completed(coach, draft, ana, lexicon)` -> a report whose
    `mistakes[0].topic` is `MistakeTopic.VERB_TENSE`.
    """
    request = CoachRequest(
        sentences=[sentence.text for sentence in draft.my_sentences[:MAX_SENTENCES]],
        target_language=draft.target_language,
        home_language=home_language(person),
    )
    answer = await coach.review(request)
    if answer is None:
        return None
    return with_answer(draft, in_target_language(answer, draft, lexicon))
