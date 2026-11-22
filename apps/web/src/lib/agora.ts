// The voice link: the Agora Web SDK (loaded from Agora's CDN, pinned, only when a session starts),
// joined with the uid of the backend's join block, publishing this browser's microphone and playing
// Mochi's voice. Thin on purpose: everything the app needs goes through the VoiceLink interface.
// No npm dependency: the few SDK calls we use are typed by hand below.

import type { AgoraJoin } from "../contracts.ts";
import { type MicProblem, micProblemOf } from "./mic.ts";

export const AGORA_SDK_URL = "https://download.agora.io/sdk/release/AgoraRTC_N-4.24.8.js";

// ---- the slice of the SDK we use ----
export interface LocalAudioTrack { getVolumeLevel(): number; stop(): void; close(): void }
export interface RemoteAudioTrack { play(): void; stop(): void; setVolume(v: number): void; getVolumeLevel(): number }
export interface RemoteUser { audioTrack?: RemoteAudioTrack }
export interface AgoraClient {
  join(appId: string, channel: string, token: string | null, uid: number): Promise<unknown>;
  publish(tracks: LocalAudioTrack[]): Promise<void>;
  subscribe(user: RemoteUser, media: "audio" | "video"): Promise<unknown>;
  on(event: "user-published", cb: (user: RemoteUser, media: "audio" | "video") => void): void;
  on(event: "user-unpublished", cb: (user: RemoteUser, media: "audio" | "video") => void): void;
  leave(): Promise<void>;
}
export interface AgoraSdk {
  createClient(config: { mode: "rtc"; codec: "vp8" }): AgoraClient;
  createMicrophoneAudioTrack(config: { AEC: boolean; ANS: boolean; AGC: boolean }): Promise<LocalAudioTrack>;
  setLogLevel?(level: number): void;
}

/** What went wrong while joining. `mic` carries the microphone problem (shown as a Session banner). */
export type VoiceFailure =
  | { kind: "agora_sdk" }
  | { kind: "agora_join" }
  | { kind: "mic"; problem: MicProblem };

export class VoiceError extends Error {
  readonly failure: VoiceFailure;
  constructor(failure: VoiceFailure, cause?: unknown) {
    super(failure.kind);
    this.name = "VoiceError";
    this.failure = failure;
    if (cause !== undefined) (this as { cause?: unknown }).cause = cause;
  }
}

export interface VoiceLink {
  /** This browser's microphone loudness, 0..1. */
  micLevel(): number;
  /** Mochi's voice loudness, 0..1, or null while no remote audio plays. */
  remoteLevel(): number | null;
  /** Mochi's voice volume, 0..100. */
  setVolume(v: number): void;
  leave(): Promise<void>;
}

let loading: Promise<AgoraSdk> | null = null;

/** Add the SDK <script> once and wait for window.AgoraRTC. */
export function loadSdk(): Promise<AgoraSdk> {
  const w = globalThis as unknown as { AgoraRTC?: AgoraSdk; document?: Document };
  if (w.AgoraRTC) return Promise.resolve(w.AgoraRTC);
  const doc = w.document;
  if (!doc) return Promise.reject(new Error("no document"));
  loading ??= new Promise<AgoraSdk>((resolve, reject) => {
    const el = doc.createElement("script");
    el.src = AGORA_SDK_URL;
    el.async = true;
    el.onload = () => (w.AgoraRTC ? resolve(w.AgoraRTC) : reject(new Error("AgoraRTC missing")));
    el.onerror = () => reject(new Error("could not load the Agora SDK"));
    doc.head.appendChild(el);
  }).catch((e: unknown) => {
    loading = null; // allow a retry
    throw e;
  });
  return loading;
}

/** Join the channel with the microphone and play Mochi's voice. Throws VoiceError. */
export async function joinVoice(join: AgoraJoin, opts: { volume: number; sdk?: () => Promise<AgoraSdk> }): Promise<VoiceLink> {
  let sdk: AgoraSdk;
  try {
    sdk = await (opts.sdk ?? loadSdk)();
  } catch (e) {
    throw new VoiceError({ kind: "agora_sdk" }, e);
  }
  try {
    sdk.setLogLevel?.(3); // warnings and errors only
  } catch {
    /* optional */
  }
  const client = sdk.createClient({ mode: "rtc", codec: "vp8" });
  let volume = clampVolume(opts.volume);
  let remote: RemoteAudioTrack | null = null;

  client.on("user-published", (user, media) => {
    if (media !== "audio") return;
    client.subscribe(user, "audio").then(() => {
      remote = user.audioTrack ?? null;
      remote?.setVolume(volume);
      remote?.play();
    }).catch(() => { /* Mochi's voice will not play; hints still work */ });
  });
  client.on("user-unpublished", (user, media) => {
    if (media === "audio" && user.audioTrack === remote) remote = null;
  });

  try {
    await client.join(join.app_id, join.channel, join.token, join.uid);
  } catch (e) {
    throw new VoiceError({ kind: "agora_join" }, e);
  }

  let mic: LocalAudioTrack;
  try {
    // Echo cancelling, noise suppression and auto gain: Mochi's voice must not come back as a turn.
    mic = await sdk.createMicrophoneAudioTrack({ AEC: true, ANS: true, AGC: true });
  } catch (e) {
    await client.leave().catch(() => undefined);
    throw new VoiceError({ kind: "mic", problem: micProblemOf(e) }, e);
  }

  try {
    await client.publish([mic]);
  } catch (e) {
    mic.stop();
    mic.close();
    await client.leave().catch(() => undefined);
    throw new VoiceError({ kind: "agora_join" }, e);
  }

  let left = false;
  return {
    micLevel: () => safeLevel(() => mic.getVolumeLevel()),
    remoteLevel: () => (remote ? safeLevel(() => remote!.getVolumeLevel()) : null),
    setVolume(v) {
      volume = clampVolume(v);
      try {
        remote?.setVolume(volume);
      } catch {
        /* ignore */
      }
    },
    async leave() {
      if (left) return;
      left = true;
      try {
        mic.stop();
        mic.close();
      } catch {
        /* already closed */
      }
      try {
        remote?.stop();
      } catch {
        /* ignore */
      }
      await client.leave().catch(() => undefined);
    },
  };
}

export function clampVolume(v: number): number {
  return Math.max(0, Math.min(100, Math.round(Number.isFinite(v) ? v : 80)));
}

function safeLevel(f: () => number): number {
  try {
    const v = f();
    return Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0;
  } catch {
    return 0;
  }
}
