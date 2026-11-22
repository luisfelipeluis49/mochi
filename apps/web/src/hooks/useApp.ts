// The wiring: one useReducer store (lib/appState.ts) + the API, the WebSocket, the microphone gate,
// the reachability probe and the voice link. Components stay thin; the decisions live in lib/.
//
// Start follows THE SHARED CONTRACT C6 exactly: (2) open the socket on the new session id,
// (3) POST start {user_id, woken_by}, (4) GET agora, (5) join with the microphone; (6) any failure
// after (3) sends POST stop.

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Language } from "../contracts.ts";
import { type Api, ApiError, realTimers } from "../lib/api.ts";
import { VoiceError } from "../lib/agora.ts";
import { type AppAction, type AppState, type Banner, appReducer, canStart, initialApp } from "../lib/appState.ts";
import { forgetUser, readUser, writeUser } from "../lib/identity.ts";
import { type ProblemKind } from "../lib/httpProblem.ts";
import { type UiLang, detectLang, storeLang, storedLang } from "../lib/i18n.ts";
import { type MicEnv, runMicGate } from "../lib/mic.ts";
import { startProbe, type Probe } from "../lib/probe.ts";
import { type Screen, pathOf, routeOf } from "../lib/routes.ts";
import { forgetSession, newSessionId, rememberSession, rememberedSession } from "../lib/sessionId.ts";
import { type SocketCtor, connectSocket, socketUrl } from "../lib/socket.ts";
import { type Outcome, ProgressStore, schedule } from "../lib/training.ts";
import { useAgoraMic, type JoinVoice } from "./useAgoraMic.ts";
import { useNow } from "./useNow.ts";

export interface AppDeps {
  api: Api;
  WebSocket: SocketCtor;
  joinVoice: JoinVoice;
  micEnv: (hooks: Pick<MicEnv, "onPrompt" | "onSlow">) => MicEnv;
  /** POST .../stop while the tab closes (navigator.sendBeacon in the real app) */
  beacon: (sessionId: string) => void;
  mock: boolean;
}

export interface OnboardingState {
  busy: boolean;
  error: "invalid" | ProblemKind | null;
}

export interface AppModel {
  state: AppState;
  screen: Screen;
  now: number;
  voice: { lastHearingAt: number; lastLoudAt: number; level: number };
  hasSpeech: boolean;
  onboarding: OnboardingState;
  digestRecord: string | null;
  timeZone?: string;
}

export interface AppActions {
  navigate(s: Screen): void;
  start(): void;
  stop(): void;
  rejoin(): void;
  retryGate(): void;
  continueWithoutMic(): void;
  retryProbe(): void;
  setVolume(v: number): void;
  dismissBanner(): void;
  dismissSaved(): void;
  submitName(v: { display_name: string; comfortable_language: Language; target_language: Language }): void;
  setLang(l: UiLang): void;
  forget(): void;
  trainingResult(wordId: string, outcome: Outcome): void;
  selectRecord(id: string): void;
}

export function bannerOf(e: unknown): Banner {
  if (e instanceof VoiceError) {
    return e.failure.kind === "mic" ? { type: "mic", kind: e.failure.problem } : { type: "http", kind: e.failure.kind };
  }
  if (e instanceof ApiError) return { type: "http", kind: e.kind };
  return { type: "http", kind: "server" };
}

const OPEN_WAIT_MS = 4000;

export function useApp(deps: AppDeps): { model: AppModel; actions: AppActions } {
  const { api } = deps;
  const progressStore = useMemo(() => new ProgressStore(), []);
  const [state, rawDispatch] = useReducer(appReducer, undefined, () => {
    const user = readUser();
    return initialApp({
      lang: detectLang({ search: location.search, stored: storedLang(), navigatorLanguage: navigator.language }),
      user,
      sessionId: rememberedSession() ?? newSessionId(),
      online: navigator.onLine !== false,
      progress: user ? progressStore.read(user.user_id) : {},
    });
  });
  const stateRef = useRef(state);
  stateRef.current = state;
  const dispatch = rawDispatch as (a: AppAction) => void;

  const [screen, setScreen] = useState<Screen>(() => routeOf(location.pathname).screen);
  const [onboarding, setOnboarding] = useState<OnboardingState>({ busy: false, error: null });
  const [digestRecord, setDigestRecord] = useState<string | null>(null);
  const mic = useAgoraMic(deps.joinVoice);
  const micRef = useRef(mic);
  micRef.current = mic;
  const live = state.phase === "capturing" || state.phase === "starting" || state.phase === "stopping";
  const now = useNow(live ? 250 : 1000);
  const hasSpeech = useMemo(() => {
    const w = globalThis as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown };
    return !!(w.SpeechRecognition || w.webkitSpeechRecognition);
  }, []);

  // ---- routing ----
  const navigate = useCallback((s: Screen) => {
    const path = pathOf(s) + (deps.mock ? "?mock=1" : "");
    if (location.pathname !== pathOf(s)) history.pushState(null, "", path);
    setScreen(s);
    globalThis.scrollTo?.(0, 0);
  }, [deps.mock]);
  useEffect(() => {
    const r = routeOf(location.pathname);
    if (r.redirected) history.replaceState(null, "", pathOf(r.screen) + location.search);
    const onPop = () => setScreen(routeOf(location.pathname).screen);
    addEventListener("popstate", onPop);
    return () => removeEventListener("popstate", onPop);
  }, []);

  // ---- no user: the URL is /welcome; a known user never stays on /welcome ----
  useEffect(() => {
    if (!state.user && location.pathname !== pathOf("welcome")) {
      history.replaceState(null, "", pathOf("welcome") + location.search);
      setScreen("welcome");
    } else if (state.user && state.identity === "ok" && screen === "welcome") {
      history.replaceState(null, "", pathOf("session") + location.search);
      setScreen("session");
    }
  }, [state.user, state.identity, screen]);

  // ---- <html lang> ----
  useEffect(() => {
    document.documentElement.lang = state.lang;
  }, [state.lang]);

  // ---- microphone gate (first, in parallel with the probe) ----
  const gateRun = useRef(0);
  const runGate = useCallback(async (keepSkipped = false) => {
    const run = ++gateRun.current;
    const before = stateRef.current.gate;
    const current = () => run === gateRun.current;
    dispatch({ type: "gate", gate: { status: "checking" } });
    const r = await runMicGate(deps.micEnv({
      onPrompt: () => { if (current()) dispatch({ type: "gate", gate: { status: "prompt" } }); },
      onSlow: () => { if (current()) dispatch({ type: "gate", gate: { status: "slow" } }); },
    }));
    if (!current()) return r; // a newer run (a tap on "Allow microphone") decides
    if (r.ok) dispatch({ type: "gate", gate: { status: "ok" } });
    else if (keepSkipped && before.status === "skipped") dispatch({ type: "gate", gate: { status: "skipped", problem: r.problem } });
    else dispatch({ type: "gate", gate: { status: "failed", problem: r.problem } });
    return r;
  }, [deps]);
  useEffect(() => {
    void runGate();
  }, [runGate]);

  // ---- reachability probe ----
  const probeRef = useRef<Probe | null>(null);
  useEffect(() => {
    const p = startProbe(api, {
      timers: realTimers, now: () => Date.now(), online: () => navigator.onLine !== false,
      onState: (s) => dispatch({ type: "probe", probe: s }),
    });
    probeRef.current = p;
    return () => p.stop();
  }, [api]);

  // ---- online / offline ----
  useEffect(() => {
    const on = () => dispatch({ type: "online", online: true });
    const off = () => dispatch({ type: "online", online: false });
    addEventListener("online", on);
    addEventListener("offline", off);
    return () => { removeEventListener("online", on); removeEventListener("offline", off); };
  }, []);

  // ---- the lost-user rule (C6) ----
  const lostUser = useCallback(() => {
    forgetUser();
    forgetSession();
    void micRef.current.leave();
    dispatch({ type: "lost_user" });
    history.replaceState(null, "", pathOf("welcome") + (deps.mock ? "?mock=1" : ""));
    setScreen("welcome");
  }, [deps.mock]);

  // ---- identity check ----
  const userId = state.user?.user_id ?? null;
  useEffect(() => {
    const u = stateRef.current.user;
    if (state.probe.status !== "ok" || !u || state.identity !== "checking") return;
    let gone = false;
    api.getUser(u.user_id).then((fresh) => {
      if (gone) return;
      writeUser(fresh);
      dispatch({ type: "identity_ok", user: fresh });
    }).catch((e: unknown) => {
      if (gone) return;
      if (e instanceof ApiError && e.status === 404) lostUser();
      else dispatch({ type: "identity_ok", user: u }); // a network error or 5xx never forgets the user
    });
    return () => { gone = true; };
  }, [api, state.probe.status, state.identity, userId, lostUser]);

  // ---- words, records, progress ----
  const refresh = useCallback(async () => {
    const u = stateRef.current.user;
    if (!u) return;
    try {
      const [words, records] = await Promise.all([api.words(u.user_id), api.sessions(u.user_id)]);
      dispatch({ type: "words", words });
      dispatch({ type: "records", records });
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) lostUser();
    }
  }, [api, lostUser]);
  useEffect(() => {
    if (state.identity !== "ok" || !userId) return;
    dispatch({ type: "progress", progress: progressStore.read(userId) });
    void refresh();
  }, [state.identity, userId, refresh, progressStore]);
  useEffect(() => {
    if ((screen === "digest" || screen === "analytics") && state.identity === "ok") void refresh();
  }, [screen, state.identity, refresh]);

  // ---- WebSocket: open for the life of the app on ?user=&session= ----
  const openWaiters = useRef<(() => void)[]>([]);
  /** POST start succeeded for the session being started (the server is capturing before the mic joins) */
  const startPosted = useRef(false);
  useEffect(() => {
    if (state.identity !== "ok" || !userId) return;
    const c = connectSocket(socketUrl(location, userId, state.sessionId), {
      onOpen: () => {
        dispatch({ type: "live", action: { type: "connected" } });
        dispatch({ type: "socket", status: "open" });
        openWaiters.current.splice(0).forEach((f) => f());
      },
      onEvent: (event) => dispatch({ type: "live", action: { type: "event", event, now: Date.now() } }),
      onClose: () => dispatch({ type: "socket", status: "retrying" }),
      onLostUser: lostUser,
    }, { WebSocket: deps.WebSocket, timers: realTimers });
    return () => {
      c.close();
      dispatch({ type: "socket", status: "idle" });
    };
  }, [state.identity, userId, state.sessionId, deps.WebSocket, lostUser]);

  const waitOpen = () => new Promise<void>((resolve) => {
    openWaiters.current.push(resolve);
    setTimeout(resolve, OPEN_WAIT_MS);
  });

  // ---- leave the voice link whenever the session is no longer ours to listen to ----
  useEffect(() => {
    if (state.phase === "idle" && micRef.current.active) void micRef.current.leave();
  }, [state.phase]);
  useEffect(() => {
    const s = state.live.session;
    if (s && !s.capturing && state.phase === "idle" && rememberedSession() === state.sessionId) forgetSession();
  }, [state.live.session, state.phase, state.sessionId]);

  // ---- closing the tab: stop only on pagehide while capturing (never on visibilitychange) ----
  useEffect(() => {
    const onHide = () => {
      const s = stateRef.current;
      if (s.phase === "capturing" || (s.phase === "starting" && startPosted.current)) deps.beacon(s.sessionId);
    };
    addEventListener("pagehide", onHide);
    return () => removeEventListener("pagehide", onHide);
  }, [deps]);

  // ---- actions ----
  const start = useCallback(async () => {
    const s = stateRef.current;
    if (!canStart(s) || !s.user) return;
    const id = newSessionId();
    rememberSession(id);
    const opened = waitOpen();
    dispatch({ type: "start_begin", sessionId: id });
    await opened;
    let started = false;
    try {
      await api.start(id, s.user.user_id, s.lang);
      started = true;
      startPosted.current = true;
      const join = await api.agora(id);
      await micRef.current.join(join, s.volume);
      startPosted.current = false;
      dispatch({ type: "start_ok", now: Date.now() });
    } catch (e) {
      startPosted.current = false;
      if (started) await api.stop(id).catch(() => null);
      await micRef.current.leave();
      forgetSession();
      const b = bannerOf(e);
      if (b.type === "http" && b.kind === "profile_lost") lostUser();
      else dispatch({ type: "start_failed", banner: b });
    }
  }, [api, lostUser]);

  const stop = useCallback(async () => {
    const s = stateRef.current;
    if (s.phase === "stopping") return;
    dispatch({ type: "stop_begin" });
    await micRef.current.leave();
    await api.stop(s.sessionId).catch(() => null);
    forgetSession();
    const end = Date.now();
    let saved = { minutes: s.startedAt ? Math.round((end - s.startedAt) / 6000) / 10 : 0, hints: s.live.sessionHints.length };
    if (s.user) {
      try {
        const records = await api.sessions(s.user.user_id);
        dispatch({ type: "records", records });
        const r = records.find((x) => x.session_id === s.sessionId);
        if (r) saved = { minutes: r.minutes, hints: r.hint_count };
      } catch {
        /* keep the local numbers */
      }
    }
    dispatch({ type: "stop_done", now: Date.now(), saved });
  }, [api]);

  const rejoin = useCallback(async () => {
    const s = stateRef.current;
    try {
      const join = await api.agora(s.sessionId);
      await micRef.current.join(join, s.volume);
      dispatch({ type: "rejoin_ok", now: Date.now() });
    } catch (e) {
      await micRef.current.leave();
      const b = bannerOf(e);
      if (b.type === "http" && b.kind === "session_ended") forgetSession();
      dispatch({ type: "voice_failed", banner: b });
    }
  }, [api]);

  const submitName = useCallback(async (v: { display_name: string; comfortable_language: Language; target_language: Language }) => {
    setOnboarding({ busy: true, error: null });
    if (stateRef.current.gate.status === "skipped") await runGate(true); // this click is the gesture iOS needs
    try {
      const user = await api.createUser(v);
      writeUser(user);
      dispatch({ type: "user_created", user });
      setOnboarding({ busy: false, error: null });
      navigate("session");
    } catch (e) {
      // 422: the inline name message. A network error or 5xx: the unreachable banner (the name is kept).
      const error = e instanceof ApiError && e.status === 422 ? "invalid" : e instanceof ApiError && e.kind === "offline" ? "offline" : "unreachable";
      setOnboarding({ busy: false, error });
    }
  }, [api, navigate, runGate]);

  const actions: AppActions = {
    navigate,
    start: () => void start(),
    stop: () => void stop(),
    rejoin: () => void rejoin(),
    retryGate: () => void runGate(true),
    continueWithoutMic: () => {
      const g = stateRef.current.gate;
      dispatch({ type: "gate", gate: { status: "skipped", problem: g.status === "failed" || g.status === "skipped" ? g.problem : "unknown" } });
    },
    retryProbe: () => probeRef.current?.retryNow(),
    setVolume: (v) => {
      mic.setVolume(v);
      dispatch({ type: "volume", volume: v, now: Date.now() });
    },
    dismissBanner: () => dispatch({ type: "banner", banner: null }),
    dismissSaved: () => dispatch({ type: "dismiss_saved" }),
    submitName: (v) => void submitName(v),
    setLang: (l) => {
      storeLang(l);
      dispatch({ type: "lang", lang: l });
    },
    forget: () => void (async () => {
      if (stateRef.current.phase === "capturing") await stop(); // before forgetting, so its card never shows for the next person
      forgetUser();
      forgetSession();
      dispatch({ type: "forget_user" });
      navigate("welcome");
    })(),
    trainingResult: (id, outcome) => {
      const s = stateRef.current;
      if (!s.user) return;
      const progress = { ...s.progress, [id]: schedule(s.progress[id], outcome, Date.now()) };
      progressStore.write(s.user.user_id, progress);
      dispatch({ type: "progress", progress });
    },
    selectRecord: setDigestRecord,
  };

  return {
    model: {
      state, screen, now, hasSpeech, onboarding, digestRecord,
      voice: { lastHearingAt: mic.lastHearingAt, lastLoudAt: mic.lastLoudAt, level: mic.level },
    },
    actions,
  };
}
