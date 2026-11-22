// Training (/training): spaced recall from the saved words (section 3.4). The prompt is the meaning;
// the answer is typed (always) or spoken (only when the browser has SpeechRecognition).
// Training never writes to the backend and never changes a word's learning_state.

import { type FormEvent, useEffect, useRef, useState } from "react";
import type { LearningEvent } from "../contracts.ts";
import { relative } from "../lib/format.ts";
import { type UiLang, plural, t } from "../lib/i18n.ts";
import { type Outcome, type Progress, ROUND_SIZE, checkAnswer, dueCards, isTrainable, nextDue, speechLang } from "../lib/training.ts";
import { Icon } from "../ui/Icons.tsx";

export interface Feedback {
  outcome: Outcome;
  expected: string;
}

export interface CardProps {
  lang: UiLang;
  word: LearningEvent;
  index: number;
  total: number;
  feedback: Feedback | null;
  hasSpeech: boolean;
  listening: boolean;
  onAnswer: (given: string) => void;
  onDontKnow: () => void;
  onNext: () => void;
  onSay: () => void;
}

export function TrainingCard(p: CardProps) {
  const { lang, word } = p;
  const [answer, setAnswer] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setAnswer(""); inputRef.current?.focus(); }, [word.learning_event_id]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (p.feedback) p.onNext();
    else p.onAnswer(answer);
  };
  const fb = p.feedback;
  return (
    <form className="card training-card" onSubmit={submit}>
      <p className="training-progress" aria-label={t(lang, "training_progress", { i: p.index + 1, n: p.total })}>{t(lang, "training_progress", { i: p.index + 1, n: p.total })}</p>
      <p className="training-question">{t(lang, word.target_language === "en" ? "training_prompt_en" : "training_prompt_pt-BR")}</p>
      <p className="training-meaning">{word.meaning}</p>
      <label className="visually-hidden" htmlFor="training-answer">{t(lang, "training_answer_label")}</label>
      <input
        id="training-answer" ref={inputRef} className="field field-big" type="text" lang={word.target_language}
        autoCapitalize="off" autoCorrect="off" spellCheck={false} autoComplete="off" value={answer}
        onChange={(e) => setAnswer(e.target.value)} readOnly={fb !== null} placeholder={t(lang, "training_answer_label")}
      />
      <div aria-live="polite" className="training-feedback">
        {fb?.outcome === "correct" && <p className="fb fb-right"><Icon name="check" size={20} /> {t(lang, "training_right")}</p>}
        {fb?.outcome === "almost" && <p className="fb fb-almost"><Icon name="check" size={20} /> {t(lang, "training_almost", { word: fb.expected })}</p>}
        {fb?.outcome === "wrong" && <p className="fb fb-wrong">{t(lang, "training_wrong", { word: fb.expected })}</p>}
      </div>
      {fb ? (
        <button type="submit" className="btn btn-primary btn-block">{t(lang, "training_next")}</button>
      ) : (
        <div className="training-actions">
          <button type="submit" className="btn btn-primary">{t(lang, "training_check")}</button>
          <button type="button" className="btn btn-secondary" onClick={p.onDontKnow}>{t(lang, "training_dont_know")}</button>
          {p.hasSpeech && (
            <span className="say-it">
              <button type="button" className="btn btn-secondary" onClick={p.onSay} disabled={p.listening}>
                <Icon name="mic" size={20} />{p.listening ? t(lang, "training_listening") : t(lang, "training_say_it")}
              </button>
              <small className="muted">{t(lang, "training_speech_note")}</small>
            </span>
          )}
        </div>
      )}
    </form>
  );
}

export function TrainingDone({ lang, right, review, nextAt, now, onAgain }: { lang: UiLang; right: number; review: number; nextAt: number | null; now: number; onAgain: () => void }) {
  return (
    <section className="card training-done" aria-live="polite">
      <p className="big-line">{t(lang, "training_done", { right, review })}</p>
      {nextAt !== null && <p className="muted">{t(lang, "training_next_due", { when: relative(nextAt, now, { lang }) })}</p>}
      <button type="button" className="btn btn-primary" onClick={onAgain}>{t(lang, "training_again")}</button>
    </section>
  );
}

export function TrainingEmpty({ lang, hasWords, nextAt, now, onGoSession }: { lang: UiLang; hasWords: boolean; nextAt: number | null; now: number; onGoSession: () => void }) {
  return (
    <section className="card empty-state">
      {hasWords && nextAt !== null ? (
        <p>{t(lang, "training_caught_up", { when: relative(nextAt, now, { lang }) })}</p>
      ) : (
        <>
          <p>{t(lang, "training_no_words")}</p>
          <a href="/session" className="btn btn-primary" onClick={(e) => { e.preventDefault(); onGoSession(); }}>{t(lang, "training_go_session")}</a>
        </>
      )}
    </section>
  );
}

interface SpeechRec {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start(): void;
}
type SpeechCtor = new () => SpeechRec;

/** window.SpeechRecognition || window.webkitSpeechRecognition, or null. */
export function speechCtor(w: unknown = globalThis): SpeechCtor | null {
  const g = w as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor } | undefined;
  return g?.SpeechRecognition ?? g?.webkitSpeechRecognition ?? null;
}

export interface TrainingScreenProps {
  lang: UiLang;
  userId: string;
  words: LearningEvent[];
  progress: Progress;
  now: number;
  hasSpeech: boolean;
  onResult: (wordId: string, outcome: Outcome) => void;
  onGoSession: () => void;
}

export function TrainingScreen(p: TrainingScreenProps) {
  const { lang } = p;
  const mine = p.words.filter((w) => w.user_id === p.userId);
  const trainable = mine.filter((w) => isTrainable(w, p.userId));
  const untrainable = mine.length - trainable.length;
  const [round, setRound] = useState(() => dueCards(trainable, p.progress, p.now, ROUND_SIZE).map((w) => w.learning_event_id));
  const [index, setIndex] = useState(0);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [score, setScore] = useState({ right: 0, review: 0 });
  const [listening, setListening] = useState(false);

  // a word saved during an empty screen starts a round
  const trainableIds = trainable.map((w) => w.learning_event_id).join();
  useEffect(() => {
    if (round.length === 0) setRound(dueCards(trainable, p.progress, Date.now(), ROUND_SIZE).map((w) => w.learning_event_id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trainableIds]);

  const byId = new Map(trainable.map((w) => [w.learning_event_id, w]));
  const cards = round.map((id) => byId.get(id)).filter((w): w is LearningEvent => !!w);
  const current = cards[index] ?? null;

  const answer = (given: string) => {
    if (!current) return;
    const outcome = checkAnswer(current.expression, given, current.target_language);
    setFeedback({ outcome, expected: current.expression });
    setScore((s) => (outcome === "wrong" ? { ...s, review: s.review + 1 } : { ...s, right: s.right + 1 }));
    p.onResult(current.learning_event_id, outcome);
  };
  const next = () => {
    setFeedback(null);
    setIndex((i) => i + 1);
  };
  const again = () => {
    setRound(dueCards(trainable, p.progress, Date.now(), ROUND_SIZE).map((w) => w.learning_event_id));
    setIndex(0);
    setScore({ right: 0, review: 0 });
    setFeedback(null);
  };
  const say = () => {
    const Ctor = speechCtor();
    if (!Ctor || !current) return;
    const rec = new Ctor();
    rec.lang = speechLang(current.target_language);
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => answer(e.results[0]?.[0]?.transcript ?? "");
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    setListening(true);
    try {
      rec.start();
    } catch {
      setListening(false);
    }
  };

  const finished = cards.length > 0 && index >= cards.length;
  const upcoming = nextDue(trainable, p.progress, p.now);

  return (
    <div className="screen training-screen">
      <h1>{t(lang, "training_title")}</h1>
      {current && !finished && (
        <TrainingCard lang={lang} word={current} index={index} total={cards.length} feedback={feedback} hasSpeech={p.hasSpeech}
          listening={listening} onAnswer={answer} onDontKnow={() => answer("")} onNext={next} onSay={say} />
      )}
      {finished && <TrainingDone lang={lang} right={score.right} review={score.review} nextAt={upcoming} now={p.now} onAgain={again} />}
      {cards.length === 0 && <TrainingEmpty lang={lang} hasWords={trainable.length > 0} nextAt={upcoming} now={p.now} onGoSession={p.onGoSession} />}
      {untrainable > 0 && <p className="muted small">{plural(lang, "training_no_meaning", untrainable)}</p>}
    </div>
  );
}
