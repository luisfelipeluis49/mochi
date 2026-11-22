// ?mock=1: a fake backend in the page. It implements the same Api, WebSocket and voice interfaces
// as the real ones, and plays the AGENTS.md section 2 demo (adiar -> postpone, guarda-chuva ->
// umbrella) for the stored user. Nothing leaves the browser; data lives until the page reloads.

import type { AgoraJoin, Hint, Language, LearningEvent, MochiEvent, NewUser, SessionRecord, SessionState, User } from "../contracts.ts";
import { type Api, ApiError } from "../lib/api.ts";
import type { VoiceLink } from "../lib/agora.ts";
import type { SocketLike } from "../lib/socket.ts";

const iso = (ms: number) => new Date(ms).toISOString();

interface DemoWord {
  expression: string;
  meaning: string;
  example: string;
}

/** The demo words, for a learner of English or of Portuguese. */
export function demoWords(target: Language): DemoWord[] {
  return target === "en"
    ? [
      { expression: "postpone", meaning: "adiar", example: "I need to postpone my meeting." },
      { expression: "umbrella", meaning: "guarda-chuva", example: "I forgot my umbrella at the office." },
      { expression: "queue", meaning: "fila", example: "There was a long queue at the bank." },
    ]
    : [
      { expression: "adiar", meaning: "postpone", example: "Preciso adiar minha reunião." },
      { expression: "guarda-chuva", meaning: "umbrella", example: "Esqueci meu guarda-chuva no escritório." },
      { expression: "fila", meaning: "queue", example: "Tinha uma fila enorme no banco." },
    ];
}

/** Past words and records for a new mock user, so Digest and Analytics have something to show. */
export function seedFor(user: User, now: number): { words: LearningEvent[]; records: SessionRecord[] } {
  const day = 86_400_000;
  const en = user.target_language === "en";
  const mk = (id: string, expression: string, meaning: string | null, hist: [LearningEvent["learning_state"], number][]): LearningEvent => ({
    learning_event_id: id, user_id: user.user_id, target_language: user.target_language, expression, meaning,
    detection_signal: "code_switch", hint_id: null, learning_state: hist[hist.length - 1][0],
    state_history: hist.map(([s, at]) => ({ learning_state: s, at: iso(at) })),
  });
  const y = now - day;
  const yy = now - 2 * day;
  const words = [
    mk("learn_seed_1", en ? "receipt" : "recibo", en ? "recibo" : "receipt", [["DISCOVERED", yy + 60_000], ["ASSISTED", yy + 120_000]]),
    mk("learn_seed_2", en ? "suitcase" : "mala", en ? "mala" : "suitcase", [["DISCOVERED", y + 60_000], ["ASSISTED", y + 90_000], ["REINFORCED", y + 300_000]]),
    mk("learn_seed_3", en ? "corkscrew" : "saca-rolhas", en ? "saca-rolhas" : "corkscrew", [["DISCOVERED", y + 400_000]]),
    mk("learn_seed_4", en ? "to look forward to" : "estar ansioso por", null, [["DISCOVERED", y + 500_000]]),
  ];
  const rec = (id: string, start: number, mins: number, hints: number, ids: string[]): SessionRecord => ({
    record_id: id, session_id: `w-${id.slice(-8).padStart(8, "0")}`, user_id: user.user_id, started_at: iso(start),
    ended_at: iso(start + mins * 60_000), minutes: mins, hint_count: hints, learning_event_ids: ids,
  });
  const records = [
    rec("rec_seed_0001", yy, 6.5, 1, ["learn_seed_1"]),
    rec("rec_seed_0002", y, 11, 3, ["learn_seed_2", "learn_seed_3", "learn_seed_4"]),
  ];
  return { words, records };
}

type Listener = (e: MochiEvent) => void;

interface LiveSession {
  id: string;
  userId: string;
  startedAt: number;
  hints: number;
  wordIds: string[];
  timers: ReturnType<typeof setTimeout>[];
  speakUntil: number;
}

export class MockBackend {
  users = new Map<string, User>();
  words = new Map<string, LearningEvent>();
  records: SessionRecord[] = [];
  live = new Map<string, LiveSession>();
  sockets = new Set<{ userId: string; sessionId: string; send: Listener }>();
  private seq = 0;
  private ids = 0;
  /** speed-up for tests and demos (1 = real time) */
  speed: number;
  constructor(speed = 1) {
    this.speed = speed;
  }

  addUser(u: User, now = Date.now()): User {
    this.users.set(u.user_id, u);
    const seed = seedFor(u, now);
    for (const w of seed.words) this.words.set(w.learning_event_id, w);
    this.records.push(...seed.records);
    return u;
  }

  /** Any id the page remembers is known here (the mock has no server restart to lose it). */
  userFor(id: string): User {
    const known = this.users.get(id);
    if (known) return known;
    return this.addUser({ user_id: id, display_name: id.replace(/-[0-9a-f]{6}$/, "").replace(/-/g, " ") || "Colleague", comfortable_languages: ["pt-BR"], target_language: "en" });
  }

  wordsOf(userId: string): LearningEvent[] {
    const first = (w: LearningEvent) => Date.parse(w.state_history[0]?.at ?? "") || 0;
    return [...this.words.values()].filter((w) => w.user_id === userId).sort((a, b) => first(b) - first(a));
  }

  private envelope<T extends MochiEvent["type"]>(type: T, sessionId: string, payload: Extract<MochiEvent, { type: T }>["payload"]): MochiEvent {
    return { schema_version: "0.4", event_id: `evt_m${++this.seq}`, type, session_id: sessionId, emitted_at: iso(Date.now()), sequence: this.seq, payload } as MochiEvent;
  }

  private publish(e: MochiEvent, forUser?: string): void {
    for (const s of this.sockets) {
      const isLearning = e.type === "learning_event.created" || e.type === "learning_event.updated";
      if (isLearning ? s.userId === forUser : s.sessionId === e.session_id) s.send(e);
    }
  }

  stateOf(sessionId: string): SessionState {
    const l = this.live.get(sessionId);
    return l
      ? { status: "active", mode: "together", focus: this.users.get(l.userId)?.target_language ?? "en", capturing: true, participants: [l.userId, "guest"] }
      : { status: "created", mode: "together", focus: "en", capturing: false, participants: [] };
  }

  connect(userId: string, sessionId: string, send: Listener): () => void {
    const entry = { userId, sessionId, send };
    this.sockets.add(entry);
    send(this.envelope("session.state.changed", sessionId, this.stateOf(sessionId)));
    send(this.envelope("activity.state.changed", sessionId, {
      activity_id: "describe_and_guess", round_id: null, state: "IDLE", describer_user_id: null, guesser_user_id: null,
      public_instruction: null, result: null, revealed_word: null, word_source: null,
    }));
    for (const w of this.wordsOf(userId).reverse()) send(this.envelope("learning_event.created", sessionId, w));
    return () => this.sockets.delete(entry);
  }

  start(sessionId: string, userId: string): SessionState {
    const existing = this.live.get(sessionId);
    if (existing) {
      if (existing.userId !== userId) throw new ApiError(409, "session_full", "busy");
      return this.stateOf(sessionId);
    }
    const user = this.userFor(userId);
    const l: LiveSession = { id: sessionId, userId, startedAt: Date.now(), hints: 0, wordIds: [], timers: [], speakUntil: 0 };
    this.live.set(sessionId, l);
    this.publish(this.envelope("session.state.changed", sessionId, this.stateOf(sessionId)));
    const words = demoWords(user.target_language);
    const at = (s: number, f: () => void) => l.timers.push(setTimeout(f, (s * 1000) / this.speed));
    at(2.5, () => this.speakLine(l, user.target_language === "en" ? "Hi! I'm listening." : "Oi! Estou ouvindo."));
    at(7, () => this.hint(l, user, words[0], "code_switch"));
    at(17, () => this.hint(l, user, words[1], "code_switch"));
    at(24, () => this.assist(l, words[0].expression));
    at(31, () => {
      this.hint(l, user, words[2], "asks_mochi");
      this.speakLine(l, user.target_language === "en" ? `You can say: ${words[2].expression}.` : `Você pode dizer: ${words[2].expression}.`);
    });
    return this.stateOf(sessionId);
  }

  private speakLine(l: LiveSession, text: string): void {
    const lang = this.users.get(l.userId)?.target_language ?? "en";
    l.speakUntil = Date.now() + 600 + text.split(/\s+/).length * 330;
    this.publish(this.envelope("agent.speak.requested", l.id, { text, language: lang, reason: "asks_mochi" }));
  }

  private hint(l: LiveSession, user: User, w: DemoWord, reason: Hint["reason"]): void {
    const now = Date.now();
    const hint: Hint = {
      hint_id: `hint_m${++this.ids}`, target_user_id: user.user_id, target_language: user.target_language, expression: w.expression,
      meaning: w.meaning, example: w.example, reason, expires_at: iso(now + 8000),
    };
    l.hints++;
    this.publish(this.envelope("hint.created", l.id, hint));
    const id = `learn_m${this.ids}`;
    const ev: LearningEvent = {
      learning_event_id: id, user_id: user.user_id, target_language: user.target_language, expression: w.expression, meaning: w.meaning,
      detection_signal: reason, hint_id: hint.hint_id, learning_state: "DISCOVERED", state_history: [{ learning_state: "DISCOVERED", at: iso(now) }],
    };
    this.words.set(id, ev);
    if (!l.wordIds.includes(id)) l.wordIds.push(id);
    this.publish(this.envelope("learning_event.created", l.id, ev), user.user_id);
  }

  private assist(l: LiveSession, expression: string): void {
    const w = [...this.words.values()].find((x) => x.user_id === l.userId && x.expression === expression && x.learning_state === "DISCOVERED");
    if (!w) return;
    const up: LearningEvent = { ...w, learning_state: "ASSISTED", state_history: [...w.state_history, { learning_state: "ASSISTED", at: iso(Date.now()) }] };
    this.words.set(w.learning_event_id, up);
    this.publish(this.envelope("learning_event.updated", l.id, up), l.userId);
  }

  stop(sessionId: string): SessionState {
    const l = this.live.get(sessionId);
    if (l) {
      l.timers.forEach(clearTimeout);
      this.live.delete(sessionId);
      const end = Date.now();
      this.records.push({
        record_id: `rec_m${++this.ids}`, session_id: sessionId, user_id: l.userId, started_at: iso(l.startedAt), ended_at: iso(end),
        minutes: Math.round((end - l.startedAt) / 6000) / 10, hint_count: l.hints, learning_event_ids: l.wordIds,
      });
    }
    const idle: SessionState = { status: "ended", mode: "together", focus: "en", capturing: false, participants: [] };
    this.publish(this.envelope("session.state.changed", sessionId, idle));
    return idle;
  }

  speaking(sessionId: string): boolean {
    return (this.live.get(sessionId)?.speakUntil ?? 0) > Date.now();
  }
}

const tick = () => new Promise((r) => setTimeout(r, 120));

export function mockApi(b: MockBackend): Api {
  return {
    health: async () => { await tick(); return { status: "ok", version: "mock" }; },
    createUser: async (body: NewUser) => {
      await tick();
      const name = body.display_name.trim();
      if (!name || name.length > 40) throw new ApiError(422, "server", "invalid");
      const slug = name.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 20).replace(/^-+|-+$/g, "") || "user";
      const id = `${slug}-${Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, "0")}`;
      return b.addUser({ user_id: id, display_name: name, comfortable_languages: [body.comfortable_language], target_language: body.target_language });
    },
    getUser: async (id) => { await tick(); return b.userFor(id); },
    words: async (id) => { await tick(); return b.wordsOf(id); },
    sessions: async (id) => {
      await tick();
      return b.records.filter((r) => r.user_id === id).sort((x, y) => Date.parse(y.ended_at) - Date.parse(x.ended_at)).slice(0, 50);
    },
    start: async (sid, userId) => { await tick(); return b.start(sid, userId); },
    stop: async (sid) => { await tick(); return b.stop(sid); },
    agora: async (sid): Promise<AgoraJoin> => {
      await tick();
      if (!b.live.has(sid)) throw new ApiError(409, "session_ended", "not capturing");
      return { app_id: "mock", channel: `mock-${sid}`, uid: 1000, token: "mock" };
    },
  };
}

/** A WebSocket class bound to the mock backend (same SocketLike shape as the browser's). */
export function mockSocketClass(b: MockBackend) {
  return class MockSocket implements SocketLike {
    onopen: SocketLike["onopen"] = null;
    onmessage: SocketLike["onmessage"] = null;
    onclose: SocketLike["onclose"] = null;
    onerror: SocketLike["onerror"] = null;
    private off: (() => void) | null = null;
    constructor(url: string) {
      const q = new URL(url, "http://mock").searchParams;
      const user = q.get("user") ?? "";
      const session = q.get("session") ?? "demo";
      setTimeout(() => {
        this.onopen?.({});
        this.off = b.connect(user, session, (e) => this.onmessage?.({ data: JSON.stringify(e) }));
      }, 60);
    }
    close() {
      this.off?.();
      this.off = null;
      setTimeout(() => this.onclose?.({ code: 1000, reason: "" }), 0);
    }
  };
}

/** A voice link with made-up levels: the "person" talks in bursts, Mochi while a line plays. */
export function mockJoinVoice(b: MockBackend, sessionId: () => string) {
  return async (_join: AgoraJoin, _opts: { volume: number }): Promise<VoiceLink> => {
    await tick();
    const t0 = Date.now();
    return {
      micLevel: () => {
        const s = ((Date.now() - t0) / 1000) % 10;
        return s > 4 && s < 6.5 ? 0.1 + Math.random() * 0.3 : 0.01;
      },
      remoteLevel: () => (b.speaking(sessionId()) ? 0.2 + Math.random() * 0.6 : 0),
      setVolume: () => {},
      leave: async () => {},
    };
  };
}
