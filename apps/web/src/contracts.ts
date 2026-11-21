// =============================================================================
// contracts.ts  —  LANGUAGE: TypeScript (types only)
// =============================================================================
// TEMPORARY copy of AGENTS.md Section 6 (contracts v0.4).
// "Contracts" = the agreed shape of every message between backend and screens.
// These are TypeScript TYPES only: they produce no code; they let the editor warn
// you if you misspell a field (e.g. "expresion" instead of "expression").
// packages/contracts (owner: Matheus) does not exist yet. When it lands,
// delete this file and change every import of "./contracts.ts" to the
// TypeScript types exported there. Do not add or rename fields here.
//
// Lines marked "PROPOSED v0.5" are NOT in AGENTS.md yet. They come from the new product
// vision (Nov 2026) and are written up in PROPOSAL_contracts_v0.5.md for the team to approve.
// Until then, only the mock (?mock=1) sends them. Everything else is v0.4 as agreed.

export const SCHEMA_VERSION = "0.4";

// ---- Allowed values (the "canonical names" of AGENTS.md §6.3). A value outside these lists is an error.
export type Language = "en" | "pt-BR";
export type DetectionReason =
  | "code_switch" | "says_unknown" | "asks_partner" | "asks_mochi" | "trails_off"
  | "talks_around" | "restarts" | "look_alike" | "not_understood";
export type SpeakReason =
  | "asks_mochi" | "activity_host"
  | "practice_partner"; // PROPOSED v0.5: Mochi talking as your partner in Praticar mode
export type SessionStatus = "created" | "active" | "paused" | "ended";
export type SessionMode =
  | "together"   // Companhia: two people talk, Mochi listens and hints
  | "activity"   // Jogar: Describe & Guess, Mochi hosts
  | "choosing"   // PROPOSED v0.5: someone said "Oi, Mochi!" and Mochi asks which mode
  | "practice";  // PROPOSED v0.5: Praticar, one person talks with Mochi
export type GameState = "IDLE" | "ACTIVE_ROUND" | "ROUND_RESULT";
export type RoundResult = "guessed" | "skipped";
export type WordSource = "learning_event" | "stock";
export type LearningState = "DISCOVERED" | "ASSISTED" | "REINFORCED" | "USED_INDEPENDENTLY";

// ---- The payload of each event (AGENTS.md §6.2) ----

// session.state.changed: is Mochi listening, and in which mode
export interface Session {
  status: SessionStatus;
  mode: SessionMode;
  focus: Language;
  capturing: boolean;
  participants: string[];
}

// hint.created: one word to help a stuck speaker.
// Convention (no field change): `expression` may hold up to 3 options separated by " · ",
// e.g. "me queimei · tomei muito sol". Screens show one option per line.
export interface Hint {
  hint_id: string;
  target_user_id: string | null;
  target_language: Language;
  expression: string;
  meaning: string | null;
  example: string | null;
  reason: DetectionReason;
  expires_at: string;
}

// activity.state.changed: the public game state (never contains the secret word during a round)
export interface Activity {
  activity_id: string;
  round_id: string | null;
  state: GameState;
  describer_user_id: string | null;
  guesser_user_id: string | null;
  public_instruction: string | null;
  result: RoundResult | null;
  revealed_word: string | null;
  word_source: WordSource | null;
}

// activity.private_prompt: the SECRET word, sent only to Mochi's screen
export interface PrivatePrompt {
  round_id: string;
  describer_user_id: string;
  secret_word: string;
  source_learning_event_id: string | null;
}

export interface StateHistoryEntry { learning_state: LearningState; at: string }

// learning_event.created / .updated: one saved word for one person (a card in "My words")
export interface LearningEvent {
  learning_event_id: string;
  user_id: string | null;
  target_language: Language;
  expression: string;
  meaning: string | null;
  detection_signal: DetectionReason;
  hint_id: string | null;
  learning_state: LearningState;
  state_history: StateHistoryEntry[];
}

// agent.speak.requested: Mochi is about to say something out loud
export interface Speak { text: string; language: Language; reason: SpeakReason }

// Links each event name to its payload type
// PROPOSED v0.5 — session.summary.created: the "after the session" card on that person's phone
// (Mochi Mobile slide: practice time, strong point, to review, new expressions, next step).
// Sent to that user's Mobile view only, when the session stops.
export interface SessionSummary {
  summary_id: string;
  user_id: string;
  target_language: Language;   // the language this person is practicing
  speaking_minutes: number;    // minutes of speaking practice in this session
  strengths: string[];         // "Ponto forte", e.g. ["Descrever objetos"]
  to_review: string[];         // "Para revisar", e.g. ["Pretérito: fui, comprei"]
  new_expressions: string[];   // "Expressões novas", e.g. ["apesar de", "na verdade"]
  next_step: string | null;    // "Próximo passo", e.g. "Descreva e Adivinhe: histórias"
  created_at: string;
}

export interface PayloadByType {
  "session.state.changed": Session;
  "hint.created": Hint;
  "hint.cleared": { hint_id: string };
  "activity.state.changed": Activity;
  "activity.private_prompt": PrivatePrompt;
  "learning_event.created": LearningEvent;
  "learning_event.updated": LearningEvent;
  "agent.speak.requested": Speak;
  "session.summary.created": SessionSummary; // PROPOSED v0.5
}

export type EventType = keyof PayloadByType;

// The full message (envelope + payload) as it arrives on the WebSocket (AGENTS.md §6.1)
export type MochiEvent = {
  [K in EventType]: {
    schema_version: string;
    event_id: string;
    type: K;
    session_id: string;
    emitted_at: string;
    sequence: number;
    payload: PayloadByType[K];
  };
}[EventType];

// The order of the steps on a word card's path
export const LEARNING_STATE_ORDER: LearningState[] = [
  "DISCOVERED", "ASSISTED", "REINFORCED", "USED_INDEPENDENTLY",
];
