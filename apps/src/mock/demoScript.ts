// =============================================================================
// demoScript.ts  —  LANGUAGE: TypeScript
// =============================================================================
// A FAKE BACKEND that replays the demo, so the screens work without Luís's backend.
// Turn it on with ?mock=1 (and ?speed=4 to make it 4x faster).
//
// The story follows the product vision slides (Nov 2026). The two people are Ana and Sophie by
// default; ?people=tasnim,matheus puts your own names in (first learns English, second Portuguese).
// Mochi shows whose voice it hears (speaker.changed, PROPOSED v0.5) as each person talks.
//   Ana learns English, Sophie learns Portuguese. They sit at a café with Mochi.
//   1. Start → someone says "Oi, Mochi!" → Mochi asks "What do you want to do today?"
//   2. Companhia: Sophie gets stuck ("e eu... hmm") → hint "me queimei · tomei muito sol".
//      Ana says "adiar" → hint "postpone". Sophie asks Mochi for "sunscreen" → Mochi says
//      "Protetor solar." out loud. Ana says "guarda-chuva" → hint "umbrella".
//   3. Jogar: Ana describes "umbrella" (only she sees it), Sophie guesses,
//      Mochi says "Correct! Sophie, your turn to describe."
//   4. Each phone gets its session summary (PROPOSED v0.5) and its word cards.
//   Each phone also starts with one earlier session (yesterday) for the "Sessions" bars,
//   and four analysed past conversations for the "My conversations" page (/me).
//
// This is NOT how visibility works for real: the gateway decides that. The mock
// only imitates the gateway's routing table so each page sees what it would see.
// =============================================================================

import {
  SCHEMA_VERSION,
  type Activity, type EventType, type Language, type LearningEvent, type LearningState, type MochiEvent,
  type ConversationReport, type PayloadByType, type RoundResult, type Session, type SessionSummary,
} from "../contracts.ts";
import { displayName } from "../lib/i18n.ts";
import type { Who } from "../lib/who.ts";

/** Who receives which event (AGENTS.md §6.2 "Sent to"). Copied here ONLY so the mock behaves like
 *  the real backend; in real life Luís's gateway decides this, never the browser. */
export function mockWouldDeliver(event: MochiEvent, who: Who): boolean {
  switch (event.type) {
    case "session.state.changed":
    case "activity.state.changed":
    case "agent.speak.requested":
      return true;
    case "hint.created": {
      const t = event.payload.target_user_id;
      return who.kind !== "user" || t === null || t === who.user;
    }
    case "hint.cleared":
      return true;
    case "activity.private_prompt":
      return who.kind === "device";
    case "learning_event.created":
    case "learning_event.updated":
      return who.kind === "user" && event.payload.user_id !== null && event.payload.user_id === who.user;
    case "session.summary.created": // PROPOSED v0.5: only that person's phone
      return who.kind === "user" && event.payload.user_id === who.user;
    case "conversation.report.created": // PROPOSED v0.5: only that person's phone
      return who.kind === "user" && event.payload.user_id === who.user;
    case "speaker.changed":            // PROPOSED v0.5: every connection
      return true;
  }
}

/** The two summaries at the end of the demo (texts from the Mochi Mobile slide). user_id "B" = the person
 *  learning Portuguese, "A" = the person learning English; replaced by the real ids on emit. */
const SUMMARIES: Omit<SessionSummary, "summary_id" | "created_at">[] = [
  {
    user_id: "B", target_language: "pt-BR", speaking_minutes: 24,
    strengths: ["Descrever objetos"], to_review: ["Pretérito: fui, comprei"],
    new_expressions: ["me queimei", "protetor solar"], next_step: "Descreva e Adivinhe: histórias",
  },
  {
    user_id: "A", target_language: "en", speaking_minutes: 24,
    strengths: ["Describing objects"], to_review: ["Past tense: went, bought"],
    new_expressions: ["postpone", "umbrella"], next_step: "Describe & Guess: stories",
  },
];

/** Tasnim's four past conversations for the "My conversations" page (/me), English practice at work and
 *  with friends (also used for any other name).
 *  Mistakes go down over the week, so the trend shows progress. daysAgo is turned into a date on connect. */
/** One sentence in the mock: [minutes after the start, what was said, the better sentence or null, mistake topic or null]. */
type Line = [number, string, string | null, string | null];

const PAST_CONVERSATIONS: (Omit<ConversationReport, "report_id" | "user_id" | "started_at" | "ended_at" | "my_sentences">
  & { daysAgo: number; lines: Line[] })[] = [
  {
    daysAgo: 6, title: "Weekly sync with the team", context: "meeting", target_language: "en", speaking_minutes: 18,
    lines: [[1, "Good morning everyone.", null, null],
      [3, "Yesterday I send the report to the client.", "Yesterday I sent the report to the client.", "Past tense"],
      [6, "I'm good in Excel, so I can do the numbers.", "I'm good at Excel, so I can do the numbers.", "Prepositions"],
      [9, "I pretend to finish it today.", "I intend to finish it today.", "False friends"],
      [12, "Maybe we need to adiar the meeting.", "Maybe we need to postpone the meeting.", null],
      [15, "What is the date to finish?", "What is the deadline?", null]],
    mistakes: [
      { kind: "grammar", topic: "Past tense", said: "Yesterday I send the report to the client.", better: "Yesterday I sent the report to the client.", count: 4 },
      { kind: "grammar", topic: "Prepositions", said: "I'm good in Excel.", better: "I'm good at Excel.", count: 2 },
      { kind: "false_friend", topic: "False friends", said: "I pretend to finish it today.", better: "I intend to finish it today.", count: 1 },
    ],
    unknown_words: [
      { expression: "postpone", meaning: "adiar", said_instead: "adiar", times: 2 },
      { expression: "deadline", meaning: "prazo", said_instead: "the date to finish", times: 1 },
    ],
    strengths: ["Explaining your work"], focus_next: [],
  },
  {
    daysAgo: 4, title: "Call with a client", context: "meeting", target_language: "en", speaking_minutes: 25,
    lines: [[1, "Thank you for your time today.", null, null],
      [4, "Last week we receive your email.", "Last week we received your email.", "Past tense"],
      [8, "Can I make a question about the nota fiscal?", "Can I ask a question about the invoice?", "make / do / ask"],
      [13, "We talked in the meeting on Monday about it.", "We talked about it in the meeting on Monday.", "Prepositions"],
      [19, "I will send news later about this.", "I will follow up on this later.", null]],
    mistakes: [
      { kind: "grammar", topic: "Past tense", said: "Last week we receive your email.", better: "Last week we received your email.", count: 3 },
      { kind: "word_choice", topic: "make / do / ask", said: "Can I make a question?", better: "Can I ask a question?", count: 2 },
      { kind: "grammar", topic: "Prepositions", said: "We talked in the meeting on Monday about it.", better: "We talked about it in the meeting on Monday.", count: 1 },
    ],
    unknown_words: [
      { expression: "follow up", meaning: "dar retorno", said_instead: "send news later", times: 1 },
      { expression: "invoice", meaning: "nota fiscal", said_instead: "nota fiscal", times: 2 },
    ],
    strengths: ["Asking clear questions"], focus_next: [],
  },
  {
    daysAgo: 2, title: "Coffee with Sophie", context: "conversation", target_language: "en", speaking_minutes: 30,
    lines: [[2, "On Saturday I go to the beach.", "On Saturday I went to the beach.", "Past tense"],
      [7, "Actually I live in São Paulo.", "Currently I live in São Paulo.", "False friends"],
      [12, "It started to rain and I didn't have a guarda-chuva.", "It started to rain and I didn't have an umbrella.", null],
      [20, "It was a really nice day anyway.", null, null]],
    mistakes: [
      { kind: "grammar", topic: "Past tense", said: "On Saturday I go to the beach.", better: "On Saturday I went to the beach.", count: 2 },
      { kind: "false_friend", topic: "False friends", said: "Actually I live in São Paulo.", better: "Currently I live in São Paulo.", count: 1 },
    ],
    unknown_words: [{ expression: "umbrella", meaning: "guarda-chuva", said_instead: "guarda-chuva", times: 1 }],
    strengths: ["Telling a story"], focus_next: [],
  },
  {
    daysAgo: 1, title: "Weekly sync with the team", context: "meeting", target_language: "en", speaking_minutes: 20,
    lines: [[1, "Hi team, quick update from me.", null, null],
      [4, "I finish the slides yesterday.", "I finished the slides yesterday.", "Past tense"],
      [9, "Let me make a question.", "Let me ask a question.", "make / do / ask"],
      [14, "The prazo is on Friday.", "The deadline is on Friday.", null],
      [17, "I'll share the link after the call.", null, null]],
    mistakes: [
      { kind: "grammar", topic: "Past tense", said: "I finish the slides yesterday.", better: "I finished the slides yesterday.", count: 1 },
      { kind: "word_choice", topic: "make / do / ask", said: "Let me make a question.", better: "Let me ask a question.", count: 1 },
    ],
    unknown_words: [{ expression: "deadline", meaning: "prazo", said_instead: "prazo", times: 1 }],
    strengths: ["Explaining your work", "Asking clear questions"],
    focus_next: ["Past tense: sent, received, finished", "Ask a question (not \"make\")", "Use: deadline, postpone, follow up"],
  },
];

/** Matheus's past conversations (English practice too: team syncs with Tasnim and a demo rehearsal). */
const MATHEUS_CONVERSATIONS: typeof PAST_CONVERSATIONS = [
  {
    daysAgo: 6, title: "Weekly sync with the team", context: "meeting", target_language: "en", speaking_minutes: 15,
    lines: [[2, "She work in marketing.", "She works in marketing.", "Third person -s"],
      [6, "It depends of the client.", "It depends on the client.", "Prepositions"],
      [10, "The orçamento is not approved yet.", "The budget is not approved yet.", null]],
    mistakes: [
      { kind: "grammar", topic: "Third person -s", said: "She work in marketing.", better: "She works in marketing.", count: 3 },
      { kind: "grammar", topic: "Prepositions", said: "It depends of the client.", better: "It depends on the client.", count: 2 },
    ],
    unknown_words: [
      { expression: "budget", meaning: "orçamento", said_instead: "orçamento", times: 2 },
      { expression: "stakeholder", meaning: "parte interessada", said_instead: "the people interested", times: 1 },
    ],
    strengths: ["Presenting numbers"], focus_next: [],
  },
  {
    daysAgo: 3, title: "Demo rehearsal", context: "meeting", target_language: "en", speaking_minutes: 22,
    lines: [[3, "The device listen all the time.", "The device listens all the time.", "Third person -s"],
      [8, "We need to do a decision today.", "We need to make a decision today.", "make / do"],
      [14, "We eventually meet on Fridays.", "We sometimes meet on Fridays.", "False friends"],
      [18, "The ensaio is tomorrow.", "The rehearsal is tomorrow.", null]],
    mistakes: [
      { kind: "grammar", topic: "Third person -s", said: "The device listen all the time.", better: "The device listens all the time.", count: 2 },
      { kind: "word_choice", topic: "make / do", said: "We need to do a decision today.", better: "We need to make a decision today.", count: 2 },
      { kind: "false_friend", topic: "False friends", said: "We eventually meet on Fridays.", better: "We sometimes meet on Fridays.", count: 1 },
    ],
    unknown_words: [
      { expression: "rehearsal", meaning: "ensaio", said_instead: "ensaio", times: 1 },
      { expression: "budget", meaning: "orçamento", said_instead: "orçamento", times: 1 },
    ],
    strengths: ["Explaining how things work"], focus_next: [],
  },
  {
    daysAgo: 1, title: "Weekly sync with the team", context: "meeting", target_language: "en", speaking_minutes: 18,
    lines: [[2, "Tasnim finish the screens today.", "Tasnim finishes the screens today.", "Third person -s"],
      [7, "Let's do a decision.", "Let's make a decision.", "make / do"],
      [12, "The stakeholder wants a demo.", null, null]],
    mistakes: [
      { kind: "grammar", topic: "Third person -s", said: "Tasnim finish the screens today.", better: "Tasnim finishes the screens today.", count: 1 },
      { kind: "word_choice", topic: "make / do", said: "Let's do a decision.", better: "Let's make a decision.", count: 1 },
    ],
    unknown_words: [{ expression: "stakeholder", meaning: "parte interessada", said_instead: "stakeholder", times: 1 }],
    strengths: ["Presenting numbers", "Explaining how things work"],
    focus_next: ["Third person: she works, it depends", "Make a decision (not \"do\")", "Use: budget, stakeholder, rehearsal"],
  },
];

const MIN = 60 * 1000;
const DAY = 24 * 60 * MIN;

/** What the person says in a NEW recording made with the "Record" button on their page (/me).
 *  The first number is how far into the recording (0 = start, 1 = when they pressed Stop). Only the
 *  page owner's sentences: what the other person said is never part of the report. Used in turn. */
const NEW_RECORDINGS: { context: ConversationReport["context"]; lines: Line[]; unknown: ConversationReport["unknown_words"];
  strengths: string[]; focus_next: string[] }[] = [
  {
    context: "conversation",
    lines: [
      [0.05, "Hi Matheus, how was your weekend?", null, null],
      [0.2, "I go to the beach with my family.", "I went to the beach with my family.", "Past tense"],
      [0.4, "It was so hot and I forgot my... protetor solar.", "It was so hot and I forgot my sunscreen.", null],
      [0.6, "Tomorrow I need to present the screens to the team.", null, null],
      [0.8, "Can I make a question about the backend?", "Can I ask a question about the backend?", "make / do / ask"],
    ],
    unknown: [{ expression: "sunscreen", meaning: "protetor solar", said_instead: "protetor solar", times: 1 }],
    strengths: ["Small talk"],
    focus_next: ["Past tense: went, sent, finished", "Ask a question (not \"make\")"],
  },
  {
    context: "meeting",
    lines: [
      [0.05, "Good morning, thanks for joining.", null, null],
      [0.25, "Yesterday we finish the first version.", "Yesterday we finished the first version.", "Past tense"],
      [0.45, "The deadline is Friday, but maybe we need to adiar.", "The deadline is Friday, but maybe we need to postpone.", null],
      [0.65, "I'm good in React and TypeScript.", "I'm good at React and TypeScript.", "Prepositions"],
      [0.85, "Let's follow up next week.", null, null],
    ],
    unknown: [{ expression: "postpone", meaning: "adiar", said_instead: "adiar", times: 1 }],
    strengths: ["Using work words: deadline, follow up"],
    focus_next: ["Past tense: finished, sent", "good at (not \"in\")", "Use: postpone"],
  },
];

/** Which kind each mistake topic is. */
const TOPIC_KIND: Record<string, ConversationReport["mistakes"][number]["kind"]> = {
  "Past tense": "grammar", "Prepositions": "grammar", "Third person -s": "grammar",
  "make / do / ask": "word_choice", "make / do": "word_choice", "False friends": "false_friend",
};

/** A fake backend that lives inside the page. One per page. */
export class MockGateway {
  private seq = 0;                                   // the sequence number of the last event
  private words: Record<string, LearningEvent> = {}; // the saved words, like the real memory
  private session: Session;
  private round = 0;
  private timers: ReturnType<typeof setTimeout>[] = []; // the scheduled steps of the demo

  private readonly who: Who;
  private readonly deliver: (e: MochiEvent) => void;
  private readonly speed: number;
  private readonly clock: () => number;
  private readonly scenario: "demo" | "recording"; // demo = the café story plays by itself; recording = the /me page
  private recordStart = 0;   // when "Record" was pressed (recording scenario)
  private recordings = 0;    // how many recordings were made on this page
  private readonly a: string; // learns English (Ana in the slides; e.g. "tasnim" with ?people=tasnim,matheus)
  private readonly b: string; // learns Portuguese (Sophie in the slides; e.g. "matheus")

  constructor(who: Who, deliver: (e: MochiEvent) => void, speed = 1, clock: () => number = () => Date.now(),
    people: [string, string] = ["ana", "sophie"], scenario: "demo" | "recording" = "demo") {
    this.who = who;
    this.deliver = deliver;
    this.speed = speed;
    this.clock = clock;
    [this.a, this.b] = people;
    this.scenario = scenario;
    this.session = { status: "created", mode: "together", focus: "en", capturing: false, participants: [this.a, this.b] };
  }

  /** Mochi recognises a voice (or nobody, with null), like the Pi reports it. */
  private voice(user: string | null) {
    this.emit("speaker.changed", { name: user ? displayName(user) : null, user_id: user });
  }

  /** Build an event (envelope + payload) and deliver it, if this page would receive it. */
  private emit<K extends EventType>(type: K, payload: PayloadByType[K]) {
    this.seq += 1;
    const event = {
      schema_version: SCHEMA_VERSION,
      event_id: `evt_mock_${this.seq}`,
      type,
      session_id: "demo",
      emitted_at: new Date(this.clock()).toISOString(),
      sequence: this.seq,
      payload,
    } as MochiEvent;
    if (mockWouldDeliver(event, this.who)) this.deliver(event);
  }

  /** Run fn after ms milliseconds (divided by the speed, so ?speed=4 is 4x faster). */
  private later(ms: number, fn: () => void) {
    this.timers.push(setTimeout(fn, ms / this.speed));
  }

  /** A time as text, e.g. "2026-11-19T16:00:04.700Z", optionally in the future. */
  private iso(offsetMs = 0) {
    return new Date(this.clock() + offsetMs).toISOString();
  }

  /** Change the session (mode, listening...) and tell every page. */
  private setSession(change: Partial<Session>) {
    this.session = { ...this.session, ...change };
    this.emit("session.state.changed", this.session);
  }

  /** Send a hint for one person that disappears after 8 seconds, and save the word for them. */
  private hint(n: number, user: string, lang: Language, expression: string, meaning: string | null, example: string | null,
    reason: PayloadByType["hint.created"]["reason"], wordExpression = expression) {
    const hintId = `hint_0${n}`;
    this.emit("hint.created", {
      hint_id: hintId, target_user_id: user, target_language: lang, expression, meaning, example,
      reason, expires_at: this.iso(8000 / this.speed),
    });
    this.word(`learn_0${n}`, user, lang, hintId, wordExpression, meaning, reason, "DISCOVERED");
  }

  /** Create a saved word, or move it to a new step, adding the step to its history. */
  private word(id: string, user: string, lang: Language, hintId: string | null, expression: string, meaning: string | null,
    signal: LearningEvent["detection_signal"], state: LearningState) {
    const prev = this.words[id];
    const at = this.iso();
    const next: LearningEvent = prev
      ? { ...prev, learning_state: state, state_history: [...prev.state_history, { learning_state: state, at }] }
      : {
          learning_event_id: id, user_id: user, target_language: lang, expression, meaning,
          detection_signal: signal, hint_id: hintId, learning_state: state,
          state_history: [{ learning_state: state, at }],
        };
    this.words[id] = next;
    this.emit(prev ? "learning_event.updated" : "learning_event.created", next);
  }

  /** Mochi says something out loud. */
  private say(text: string, language: Language, reason: PayloadByType["agent.speak.requested"]["reason"]) {
    this.emit("agent.speak.requested", { text, language, reason });
  }

  /** Send a game state: A describes, B guesses (from the "Jogar" slide: Ana describes, Sophie guesses). */
  private activity(a: Partial<Activity>) {
    const base: Activity = {
      activity_id: "describe_and_guess", round_id: `round_00${this.round}`, state: "IDLE",
      describer_user_id: this.a, guesser_user_id: this.b, public_instruction: `${displayName(this.a)} describes. ${displayName(this.b)} guesses!`,
      result: null, revealed_word: null, word_source: "learning_event",
    };
    this.emit("activity.state.changed", { ...base, ...a });
  }

  /** On connect the server sends current session state (§6.4). The mock also sends each person
   *  one earlier session (yesterday), so the phone's "Sessions" bars have history to show.
   *  (For the real backend this is the "re-send on connect" question in the proposal.) */
  connect(autoplay: boolean) {
    this.emit("session.state.changed", this.session);
    const yesterday = this.iso(-24 * 60 * 60 * 1000);
    this.emit("session.summary.created", { summary_id: `sum_prev_${this.b}`, user_id: this.b, target_language: "pt-BR",
      speaking_minutes: 15, strengths: ["Fazer perguntas"], to_review: ["Gênero: o / a"], new_expressions: ["na verdade"],
      next_step: "Companhia: falar sobre o fim de semana", created_at: yesterday });
    this.emit("session.summary.created", { summary_id: `sum_prev_${this.a}`, user_id: this.a, target_language: "en",
      speaking_minutes: 12, strengths: ["Asking questions"], to_review: ["Prepositions: in / on / at"], new_expressions: ["actually"],
      next_step: "Company: talk about your weekend", created_at: yesterday });
    // The "My conversations" page: this person's past analysed conversations (any user name works in the mock).
    if (this.who.kind === "user") {
      const user = this.who.user;
      const past = user === "matheus" ? MATHEUS_CONVERSATIONS : PAST_CONVERSATIONS;
      past.forEach(({ daysAgo, lines, ...r }, i) => this.emit("conversation.report.created", {
        ...r, report_id: `rep_${user}_${i + 1}`, user_id: user,
        started_at: this.iso(-daysAgo * DAY), ended_at: this.iso(-daysAgo * DAY + Math.round(r.speaking_minutes * 1.5) * MIN),
        my_sentences: lines.map(([m, text, better, topic]) => ({ at: this.iso(-daysAgo * DAY + m * MIN), text, better, topic })),
      }));
    }
    if (autoplay) this.later(1500, () => this.start());
  }

  /** The Start button, then the whole story. On the /me page: "Record" starts a recording instead. */
  start() {
    if (this.scenario === "recording") {
      this.recordStart = this.clock();
      this.setSession({ status: "active", capturing: true, mode: "together" });
      return;
    }
    this.setSession({ status: "active", capturing: true, mode: "together" });
    // "Oi, Mochi!" → Mochi asks which mode (PROPOSED v0.5: mode "choosing")
    this.later(1500, () => {
      this.setSession({ mode: "choosing" });
      this.say("Oi! O que vocês querem fazer hoje?", "pt-BR", "asks_mochi");
    });
    // "Só escuta enquanto a gente pratica." → Companhia
    this.later(5500, () => this.setSession({ mode: "together" }));
    // B starts talking, trails off → two options on Mochi's screen
    this.later(6000, () => this.voice(this.b));
    this.later(7500, () => this.hint(1, this.b, "pt-BR", "me queimei · tomei muito sol", "I got sunburned",
      "Ontem a gente foi à praia e eu me queimei.", "trails_off", "me queimei"));
    // A talks, switches language → "postpone", then uses it
    this.later(10500, () => this.voice(this.a));
    this.later(12000, () => this.hint(2, this.a, "en", "postpone", "adiar", "I need to postpone my meeting.", "code_switch"));
    this.later(15000, () => this.word("learn_02", this.a, "en", "hint_02", "postpone", "adiar", "code_switch", "ASSISTED"));
    // B asks Mochi → Mochi answers OUT LOUD and shows it
    this.later(16000, () => this.voice(this.b));
    this.later(17000, () => {
      this.say("Protetor solar.", "pt-BR", "asks_mochi");
      this.hint(3, this.b, "pt-BR", "protetor solar", "sunscreen", null, "asks_mochi");
    });
    // A: "guarda-chuva" → "umbrella"
    this.later(19500, () => this.voice(this.a));
    this.later(21000, () => this.hint(4, this.a, "en", "umbrella", "guarda-chuva", "I forgot my umbrella at the office.", "code_switch"));
    // "Bora jogar!" → the game
    this.later(25000, () => this.voice(null));
    this.later(27000, () => this.activityStart());
  }

  /** The Stop button: stop listening and send each person's summary. On the /me page: save the recording. */
  stop() {
    if (this.scenario === "recording") {
      this.setSession({ status: "ended", capturing: false });
      this.saveRecording();
      return;
    }
    this.clear();
    this.voice(null);
    this.setSession({ status: "ended", capturing: false });
    this.summaries();
  }

  /** Send each person their summary (PROPOSED v0.5). */
  private summaries() {
    SUMMARIES.forEach((s, i) => this.emit("session.summary.created", {
      ...s, user_id: s.user_id === "A" ? this.a : this.b, summary_id: `sum_00${i + 1}`, created_at: this.iso(),
    }));
  }

  /** "Stop" on the /me page: the recording becomes ONE new conversation with only the owner's sentences. */
  private saveRecording() {
    if (this.who.kind !== "user" || this.recordStart === 0) return;
    const user = this.who.user;
    const end = this.clock();
    const length = Math.max(end - this.recordStart, 1000);
    const r = NEW_RECORDINGS[this.recordings % NEW_RECORDINGS.length];
    this.recordings += 1;
    // Group the sentences with mistakes by topic, like the backend would.
    const byTopic = new Map<string, ConversationReport["mistakes"][number]>();
    for (const [, text, better, topic] of r.lines) {
      if (!topic || !better) continue;
      const m = byTopic.get(topic);
      if (m) m.count += 1;
      else byTopic.set(topic, { kind: TOPIC_KIND[topic] ?? "grammar", topic, said: text, better, count: 1 });
    }
    this.emit("conversation.report.created", {
      report_id: `rep_${user}_new_${this.recordings}_${end}`, user_id: user, target_language: "en", title: "",
      context: r.context, started_at: new Date(this.recordStart).toISOString(), ended_at: new Date(end).toISOString(),
      speaking_minutes: Math.max(1, Math.round(length / MIN / 2)),
      my_sentences: r.lines.map(([f, text, better, topic]) => ({
        at: new Date(this.recordStart + f * length).toISOString(), text, better, topic,
      })),
      mistakes: [...byTopic.values()], unknown_words: r.unknown, strengths: r.strengths, focus_next: r.focus_next,
    });
    this.recordStart = 0;
  }

  /** Start a round: public game state for everyone, secret word for Mochi's screen only. */
  activityStart() {
    this.round += 1;
    this.setSession({ mode: "activity" });
    this.activity({ state: "ACTIVE_ROUND" });
    this.emit("activity.private_prompt", {
      round_id: `round_00${this.round}`, describer_user_id: this.a, secret_word: "umbrella",
      source_learning_event_id: "learn_04",
    });
    // In the new vision Mochi hears "An umbrella!" and ends the round itself.
    // On Mochi's own screen we wait for the tap instead, so the tap path can be tried too.
    this.later(1500, () => this.voice(this.a));   // A describes...
    this.later(6000, () => this.voice(this.b));   // ...B guesses
    if (this.who.kind !== "device") this.later(8000, () => this.activityResult("guessed"));
  }

  /** End the round. "guessed" → umbrella becomes "Recalled in a game" and Mochi congratulates. */
  activityResult(result: RoundResult) {
    this.activity({ state: "ROUND_RESULT", result, revealed_word: "umbrella" });
    if (result === "guessed") {
      this.word("learn_04", this.a, "en", "hint_04", "umbrella", "guarda-chuva", "code_switch", "REINFORCED");
      this.say(`Correct! ${displayName(this.b)}, your turn to describe.`, "en", "activity_host");
    }
    this.later(5000, () => {
      this.activity({ state: "IDLE" });
      this.setSession({ mode: "together" });
    });
    // End of the demo: the session stops and the phones show the summaries.
    this.later(8000, () => this.stop());
  }

  /** Cancel every scheduled step (when the page closes). */
  clear() {
    this.timers.forEach(clearTimeout);
    this.timers = [];
  }
}
