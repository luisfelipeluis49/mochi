// Types for the events and payloads of AGENTS.md section 6 (contracts v0.4) and for the REST shapes of
// THE SHARED CONTRACT (User, SessionRecord, AgoraJoin; docs/DECISIONS.md D-42).
// Do not add, rename or remove a field here: propose it to the owners (AGENTS.md rule 1).
// The type guards accept unknown extra keys, because the backend may send optional fields
// (the hint.created example carries "candidates" and "context").

export const SCHEMA_VERSION = "0.4";

export type Language = "en" | "pt-BR";
export type DetectionReason =
  | "code_switch" | "says_unknown" | "asks_partner" | "asks_mochi" | "trails_off"
  | "talks_around" | "restarts" | "look_alike" | "not_understood";
export type SpeakReason = "asks_mochi" | "activity_host";
export type SessionStatus = "created" | "active" | "paused" | "ended";
export type SessionMode = "together" | "activity";
export type GameState = "IDLE" | "ACTIVE_ROUND" | "ROUND_RESULT";
export type RoundResult = "guessed" | "skipped";
export type WordSource = "learning_event" | "stock";
export type LearningState = "DISCOVERED" | "ASSISTED" | "REINFORCED" | "USED_INDEPENDENTLY";

export const LANGUAGES: readonly Language[] = ["en", "pt-BR"];
export const LEARNING_STATES: readonly LearningState[] = ["DISCOVERED", "ASSISTED", "REINFORCED", "USED_INDEPENDENTLY"];

/** session.state.changed payload; also the answer of start and stop. */
export interface SessionState {
  status: SessionStatus;
  mode: SessionMode;
  focus: Language;
  capturing: boolean;
  participants: string[];
}

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

export interface PrivatePrompt {
  round_id: string;
  describer_user_id: string;
  secret_word: string;
  source_learning_event_id: string | null;
}

export interface StateHistoryEntry {
  learning_state: LearningState;
  at: string;
}

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

export interface Speak {
  text: string;
  language: Language;
  reason: SpeakReason;
}

export interface PayloadByType {
  "session.state.changed": SessionState;
  "hint.created": Hint;
  "hint.cleared": { hint_id: string };
  "activity.state.changed": Activity;
  "activity.private_prompt": PrivatePrompt;
  "learning_event.created": LearningEvent;
  "learning_event.updated": LearningEvent;
  "agent.speak.requested": Speak;
}
export type EventType = keyof PayloadByType;
export const EVENT_TYPES = [
  "session.state.changed", "hint.created", "hint.cleared", "activity.state.changed",
  "activity.private_prompt", "learning_event.created", "learning_event.updated", "agent.speak.requested",
] as const satisfies readonly EventType[];

interface EnvelopeBase<T extends EventType> {
  schema_version: string;
  event_id: string;
  type: T;
  session_id: string;
  emitted_at: string;
  sequence: number;
  payload: PayloadByType[T];
}
export type MochiEvent = { [T in EventType]: EnvelopeBase<T> }[EventType];

// ---- THE SHARED CONTRACT, C2-C6 -------------------------------------------------------

export interface User {
  user_id: string;
  display_name: string;
  comfortable_languages: Language[];
  target_language: Language;
}

export interface NewUser {
  display_name: string;
  comfortable_language: Language;
  target_language: Language;
}

export interface SessionRecord {
  record_id: string;
  session_id: string;
  user_id: string;
  started_at: string;
  ended_at: string;
  minutes: number;
  hint_count: number;
  learning_event_ids: string[];
}

export interface AgoraJoin {
  app_id: string;
  channel: string;
  uid: number;
  /** The contract says a string; null is tolerated (an Agora project without a certificate needs no token). */
  token: string | null;
}

// ---- Type guards -----------------------------------------------------------------------

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isStrOrNull = (v: unknown) => v === null || isStr(v);
const isLang = (v: unknown): v is Language => v === "en" || v === "pt-BR";
const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const oneOf = <T extends string>(list: readonly T[]) => (v: unknown): v is T => list.includes(v as T);

const isReason = oneOf<DetectionReason>([
  "code_switch", "says_unknown", "asks_partner", "asks_mochi", "trails_off",
  "talks_around", "restarts", "look_alike", "not_understood",
]);
const isLearningState = oneOf(LEARNING_STATES);

export function isSessionState(v: unknown): v is SessionState {
  return isObj(v) && oneOf<SessionStatus>(["created", "active", "paused", "ended"])(v.status)
    && oneOf<SessionMode>(["together", "activity"])(v.mode) && isLang(v.focus)
    && typeof v.capturing === "boolean" && Array.isArray(v.participants) && v.participants.every(isStr);
}

export function isHint(v: unknown): v is Hint {
  return isObj(v) && isStr(v.hint_id) && isStrOrNull(v.target_user_id) && isLang(v.target_language)
    && isStr(v.expression) && isStrOrNull(v.meaning) && isStrOrNull(v.example) && isReason(v.reason)
    && isStr(v.expires_at);
}

export function isActivity(v: unknown): v is Activity {
  return isObj(v) && isStr(v.activity_id) && isStrOrNull(v.round_id)
    && oneOf<GameState>(["IDLE", "ACTIVE_ROUND", "ROUND_RESULT"])(v.state)
    && isStrOrNull(v.describer_user_id) && isStrOrNull(v.guesser_user_id) && isStrOrNull(v.public_instruction)
    && (v.result === null || v.result === "guessed" || v.result === "skipped")
    && isStrOrNull(v.revealed_word)
    && (v.word_source === null || v.word_source === "learning_event" || v.word_source === "stock");
}

export function isPrivatePrompt(v: unknown): v is PrivatePrompt {
  return isObj(v) && isStr(v.round_id) && isStr(v.describer_user_id) && isStr(v.secret_word)
    && isStrOrNull(v.source_learning_event_id);
}

export function isLearningEvent(v: unknown): v is LearningEvent {
  return isObj(v) && isStr(v.learning_event_id) && isStrOrNull(v.user_id) && isLang(v.target_language)
    && isStr(v.expression) && isStrOrNull(v.meaning) && isReason(v.detection_signal) && isStrOrNull(v.hint_id)
    && isLearningState(v.learning_state) && Array.isArray(v.state_history)
    && v.state_history.every((h) => isObj(h) && isLearningState(h.learning_state) && isStr(h.at));
}

export function isSpeak(v: unknown): v is Speak {
  return isObj(v) && isStr(v.text) && isLang(v.language) && (v.reason === "asks_mochi" || v.reason === "activity_host");
}

const PAYLOAD_GUARDS: { [T in EventType]: (v: unknown) => boolean } = {
  "session.state.changed": isSessionState,
  "hint.created": isHint,
  "hint.cleared": (v) => isObj(v) && isStr(v.hint_id),
  "activity.state.changed": isActivity,
  "activity.private_prompt": isPrivatePrompt,
  "learning_event.created": isLearningEvent,
  "learning_event.updated": isLearningEvent,
  "agent.speak.requested": isSpeak,
};

/** A full, known event with a payload of the right shape. Unknown event types are not events here. */
export function isMochiEvent(v: unknown): v is MochiEvent {
  if (!isObj(v) || !isStr(v.type) || !(v.type in PAYLOAD_GUARDS)) return false;
  if (!isStr(v.schema_version) || !isStr(v.event_id) || !isStr(v.session_id) || !isStr(v.emitted_at) || !isNum(v.sequence)) return false;
  return PAYLOAD_GUARDS[v.type as EventType](v.payload);
}

export function isUser(v: unknown): v is User {
  return isObj(v) && isStr(v.user_id) && isStr(v.display_name) && Array.isArray(v.comfortable_languages)
    && v.comfortable_languages.length > 0 && v.comfortable_languages.every(isLang) && isLang(v.target_language);
}

export function isSessionRecord(v: unknown): v is SessionRecord {
  return isObj(v) && isStr(v.record_id) && isStr(v.session_id) && isStr(v.user_id) && isStr(v.started_at)
    && isStr(v.ended_at) && isNum(v.minutes) && isNum(v.hint_count)
    && Array.isArray(v.learning_event_ids) && v.learning_event_ids.every(isStr);
}

export function isAgoraJoin(v: unknown): v is AgoraJoin {
  return isObj(v) && isStr(v.app_id) && isStr(v.channel) && isNum(v.uid) && isStrOrNull(v.token);
}
