// Entry point: builds the real (or ?mock=1) dependencies and renders the app.
import { StrictMode, useMemo } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App.tsx";
import { type AppDeps, useApp } from "./hooks/useApp.ts";
import { beaconStop, createApi, realTimers } from "./lib/api.ts";
import { joinVoice } from "./lib/agora.ts";
import { browserMicEnv } from "./lib/mic.ts";
import type { SocketCtor } from "./lib/socket.ts";
import { MockBackend, mockApi, mockJoinVoice, mockSocketClass } from "./mock/backend.ts";
import { rememberedSession } from "./lib/sessionId.ts";
import "./styles/tokens.css";
import "./styles/app.css";

function realDeps(): AppDeps {
  return {
    api: createApi(),
    WebSocket: WebSocket as unknown as SocketCtor,
    joinVoice,
    micEnv: (hooks) => browserMicEnv(realTimers, hooks),
    beacon: (id) => void beaconStop(id),
    mock: false,
  };
}

function mockDeps(): AppDeps {
  const b = new MockBackend();
  const api = mockApi(b);
  let current = "";
  return {
    api: { ...api, start: (sid, uid, lang) => { current = sid; return api.start(sid, uid, lang); } },
    WebSocket: mockSocketClass(b),
    joinVoice: mockJoinVoice(b, () => current || rememberedSession() || ""),
    micEnv: (hooks) => browserMicEnv(realTimers, hooks),
    beacon: (id) => void api.stop(id),
    mock: true,
  };
}

function Root() {
  const deps = useMemo(() => (new URLSearchParams(location.search).get("mock") === "1" ? mockDeps() : realDeps()), []);
  const { model, actions } = useApp(deps);
  return <App model={model} actions={actions} href={location.href} />;
}

createRoot(document.getElementById("root")!).render(<StrictMode><Root /></StrictMode>);
