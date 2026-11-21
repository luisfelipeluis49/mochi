// =============================================================================
// demoScript.ts  —  LANGUAGE: TypeScript
// =============================================================================
// A FAKE BACKEND that replays the demo, so the screens work without Luís's backend.
// Turn it on with ?mock=1 (and ?speed=4 to make it 4x faster).
//
// The story follows the product vision slides (Nov 2026):
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
  }
}

/** Ana's and Sophie's summaries at the end of the demo (texts from the Mochi Mobile slide). */
const SUMMARIES: Omit<SessionSummary, "summary_id" | "created_at">[] = [
  {
    user_id: "sophie", target_language: "pt-BR", speaking_minutes: 24,
    strengths: ["Descrever objetos"], to_review: ["Pretérito: fui, comprei"],
    new_expressions: ["me queimei", "protetor solar"], next_step: "Descreva e Adivinhe: histórias",
  },
  {
    user_id: "ana", target_language: "en", speaking_minutes: 24,
    strengths: ["Describing objects"], to_review: ["Past tense: went, bought"],
    new_expressions: ["postpone", "umbrella"], next_step: "Describe & Guess: stories",
  },
];

/** Four past conversations for the "My conversations" page (/me), English practice at work and with friends.
 *  Mistakes go down over the week, so the trend shows progress. daysAgo is turned into a date on connect. */
const PAST_CONVERSATIONS: (Omit<ConversationReport, "report_id" | "user_id" | "started_at"> & { daysAgo: number })[] = [
  {
    daysAgo: 6, title: "Weekly sync with the team", context: "meeting", target_language: "en", speaking_minutes: 18,
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
    mistakes: [
      { kind: "grammar", topic: "Past tense", said: "On Saturday I go to the beach.", better: "On Saturday I went to the beach.", count: 2 },
      { kind: "false_friend", topic: "False friends", said: "Actually I live in São Paulo.", better: "Currently I live in São Paulo.", count: 1 },
    ],
    unknown_words: [{ expression: "umbrella", meaning: "guarda-chuva", said_instead: "guarda-chuva", times: 1 }],
    strengths: ["Telling a story"], focus_next: [],
  },
  {
    daysAgo: 1, title: "Weekly sync with the team", context: "meeting", target_language: "en", speaking_minutes: 20,
    mistakes: [
      { kind: "grammar", topic: "Past tense", said: "I finish the slides yesterday.", better: "I finished the slides yesterday.", count: 1 },
      { kind: "word_choice", topic: "make / do / ask", said: "Let me make a question.", better: "Let me ask a question.", count: 1 },
    ],
    unknown_words: [{ expression: "deadline", meaning: "prazo", said_instead: "prazo", times: 1 }],
    strengths: ["Explaining your work", "Asking clear questions"],
    focus_next: ["Past tense: sent, received, finished", "Ask a question (not \"make\")", "Use: deadline, postpone, follow up"],
  },
];

/** A fake backend that lives inside the page. One per page. */
export class MockGateway {
  private seq = 0;                                   // the sequence number of the last event
  private words: Record<string, LearningEvent> = {}; // the saved words, like the real memory
  private session: Session = { status: "created", mode: "together", focus: "en", capturing: false, participants: ["ana", "sophie"] };
  private round = 0;
  private timers: ReturnType<typeof setTimeout>[] = []; // the scheduled steps of the demo

  private readonly who: Who;
  private readonly deliver: (e: MochiEvent) => void;
  private readonly speed: number;
  private readonly clock: () => number;

  constructor(who: Who, deliver: (e: MochiEvent) => void, speed = 1, clock: () => number = () => Date.now()) {
    this.who = who;
    this.deliver = deliver;
    this.speed = speed;
    this.clock = clock;
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

  /** Send a game state: Ana describes, Sophie guesses (from the "Jogar" slide). */
  private activity(a: Partial<Activity>) {
    const base: Activity = {
      activity_id: "describe_and_guess", round_id: `round_00${this.round}`, state: "IDLE",
      describer_user_id: "ana", guesser_user_id: "sophie", public_instruction: "Ana describes. Sophie guesses!",
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
    this.emit("session.summary.created", { summary_id: "sum_prev_sophie", user_id: "sophie", target_language: "pt-BR",
      speaking_minutes: 15, strengths: ["Fazer perguntas"], to_review: ["Gênero: o / a"], new_expressions: ["na verdade"],
      next_step: "Companhia: falar sobre o fim de semana", created_at: yesterday });
    this.emit("session.summary.created", { summary_id: "sum_prev_ana", user_id: "ana", target_language: "en",
      speaking_minutes: 12, strengths: ["Asking questions"], to_review: ["Prepositions: in / on / at"], new_expressions: ["actually"],
      next_step: "Company: talk about your weekend", created_at: yesterday });
    // The "My conversations" page: this person's past analysed conversations (any user name works in the mock).
    if (this.who.kind === "user") {
      const user = this.who.user;
      PAST_CONVERSATIONS.forEach(({ daysAgo, ...r }, i) => this.emit("conversation.report.created", {
        ...r, report_id: `rep_${user}_${i + 1}`, user_id: user, started_at: this.iso(-daysAgo * 24 * 60 * 60 * 1000),
      }));
    }
    if (autoplay) this.later(1500, () => this.start());
  }

  /** The Start button, then the whole story. */
  start() {
    this.setSession({ status: "active", capturing: true, mode: "together" });
    // "Oi, Mochi!" → Mochi asks which mode (PROPOSED v0.5: mode "choosing")
    this.later(1500, () => {
      this.setSession({ mode: "choosing" });
      this.say("Oi! O que vocês querem fazer hoje?", "pt-BR", "asks_mochi");
    });
    // "Só escuta enquanto a gente pratica." → Companhia
    this.later(5500, () => this.setSession({ mode: "together" }));
    // Sophie trails off → two options on Mochi's screen
    this.later(7500, () => this.hint(1, "sophie", "pt-BR", "me queimei · tomei muito sol", "I got sunburned",
      "Ontem a gente foi à praia e eu me queimei.", "trails_off", "me queimei"));
    // Ana switches language → "postpone", then uses it
    this.later(12000, () => this.hint(2, "ana", "en", "postpone", "adiar", "I need to postpone my meeting.", "code_switch"));
    this.later(15000, () => this.word("learn_02", "ana", "en", "hint_02", "postpone", "adiar", "code_switch", "ASSISTED"));
    // Sophie asks Mochi → Mochi answers OUT LOUD and shows it
    this.later(17000, () => {
      this.say("Protetor solar.", "pt-BR", "asks_mochi");
      this.hint(3, "sophie", "pt-BR", "protetor solar", "sunscreen", null, "asks_mochi");
    });
    // Ana: "guarda-chuva" → "umbrella"
    this.later(21000, () => this.hint(4, "ana", "en", "umbrella", "guarda-chuva", "I forgot my umbrella at the office.", "code_switch"));
    // "Bora jogar!" → the game
    this.later(27000, () => this.activityStart());
  }

  /** The Stop button: stop listening and send each person's summary. */
  stop() {
    this.clear();
    this.setSession({ status: "ended", capturing: false });
    this.summaries();
  }

  /** Send each person their summary (PROPOSED v0.5). */
  private summaries() {
    SUMMARIES.forEach((s, i) => this.emit("session.summary.created", { ...s, summary_id: `sum_00${i + 1}`, created_at: this.iso() }));
  }

  /** Start a round: public game state for everyone, secret word for Mochi's screen only. */
  activityStart() {
    this.round += 1;
    this.setSession({ mode: "activity" });
    this.activity({ state: "ACTIVE_ROUND" });
    this.emit("activity.private_prompt", {
      round_id: `round_00${this.round}`, describer_user_id: "ana", secret_word: "umbrella",
      source_learning_event_id: "learn_04",
    });
    // In the new vision Mochi hears "An umbrella!" and ends the round itself.
    // On Mochi's own screen we wait for the tap instead, so the tap path can be tried too.
    if (this.who.kind !== "device") this.later(8000, () => this.activityResult("guessed"));
  }

  /** End the round. "guessed" → umbrella becomes "Recalled in a game" and Mochi congratulates. */
  activityResult(result: RoundResult) {
    this.activity({ state: "ROUND_RESULT", result, revealed_word: "umbrella" });
    if (result === "guessed") {
      this.word("learn_04", "ana", "en", "hint_04", "umbrella", "guarda-chuva", "code_switch", "REINFORCED");
      this.say("Correct! Sophie, your turn to describe.", "en", "activity_host");
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
