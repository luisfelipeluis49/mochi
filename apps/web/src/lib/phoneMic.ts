// =============================================================================
// phoneMic.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// THE PHONE AS MOCHI'S MICROPHONE (proposal: apps/web/PROPOSAL_phone_microphone.md).
//   - Started on the PHONE: this phone's mic listens and the hints show here.
//   - Started on the PI:    the Pi listens; this phone shows no live words, only analytics afterwards.
// SINCE D-37 each phone has its OWN session (phoneSession.ts): it joins its own Agora channel
// (GET /api/sessions/<id>/agora), so the Pi can stay on and neither disturbs the other.
// This file: (1) remembers whether THIS phone started the session, (2) joins the Agora channel with
// the phone's mic. The Agora Web SDK is loaded from Agora's CDN only when the mic starts, so the app
// has no new npm dependency and pages that never use the mic never download it.
// The mic needs HTTPS (the Vercel link); on plain http:// over Wi-Fi the browser refuses it.
// =============================================================================

/** Where to join: the answer of GET /api/sessions/<id>/agora. */
export interface AgoraJoin {
  app_id: string;
  channel: string;
  uid: number;
  token: string | null;
}

/** The Agora Web SDK (pinned version). It defines window.AgoraRTC. */
export const AGORA_SDK_URL = "https://download.agora.io/sdk/release/AgoraRTC_N-4.24.8.js";

// --- Who started the session? -----------------------------------------------------
// Kept in sessionStorage: it survives a reload of this tab, and no other phone sees it.
const KEY = "mochi.phoneSession";

/** The small part of Storage we use (so the tests can pass a fake one). */
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function storage(): Store | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null; // some private modes throw on access
  }
}

/** Remember that this phone started the session (true) or forget it (false). */
export function markStartedHere(on: boolean, s: Store | null = storage()): void {
  try {
    if (on) s?.setItem(KEY, "1");
    else s?.removeItem(KEY);
  } catch {
    // storage full or blocked: the phone just behaves as if the Pi started it
  }
}

/** Did this phone start the session that is running? */
export function startedHere(s: Store | null = storage()): boolean {
  try {
    return s?.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** Show live things (the hint, new word cards, the numbers) on this phone right now?
 *  Yes when nothing is running (analytics after the session) or when this phone started it.
 *  No while a session started on the Pi is running. */
export function showLive(capturing: boolean, here: boolean): boolean {
  return !capturing || here;
}

// --- The mic itself ---------------------------------------------------------------
// Only the few SDK calls we use, typed by hand (no npm types without the package).
interface AudioTrack { play?(): void; stop(): void; close(): void }
interface RemoteUser { audioTrack?: AudioTrack }
interface AgoraClient {
  join(appId: string, channel: string, token: string | null, uid: number): Promise<unknown>;
  publish(tracks: AudioTrack[]): Promise<void>;
  subscribe(user: RemoteUser, media: "audio" | "video"): Promise<unknown>;
  on(event: "user-published", cb: (user: RemoteUser, media: "audio" | "video") => void): void;
  leave(): Promise<void>;
}
interface AgoraSdk {
  createClient(config: { mode: "rtc"; codec: "vp8" }): AgoraClient;
  createMicrophoneAudioTrack(config: { AEC: boolean; ANS: boolean; AGC: boolean }): Promise<AudioTrack>;
}

let loading: Promise<AgoraSdk> | null = null;

/** Add the SDK <script> once and wait for window.AgoraRTC. */
function loadSdk(): Promise<AgoraSdk> {
  const w = window as unknown as { AgoraRTC?: AgoraSdk };
  if (w.AgoraRTC) return Promise.resolve(w.AgoraRTC);
  loading ??= new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = AGORA_SDK_URL;
    el.async = true;
    el.onload = () => (w.AgoraRTC ? resolve(w.AgoraRTC) : reject(new Error("AgoraRTC missing")));
    el.onerror = () => {
      loading = null; // allow a retry later
      reject(new Error("could not load the Agora SDK"));
    };
    document.head.appendChild(el);
  });
  return loading;
}

/** Join the channel with this phone's mic and play Mochi's voice. Returns a function that stops it all.
 *  Example: const stop = await startPhoneMic(join); ... await stop(); */
export async function startPhoneMic(join: AgoraJoin): Promise<() => Promise<void>> {
  const sdk = await loadSdk();
  const client = sdk.createClient({ mode: "rtc", codec: "vp8" });
  // Mochi's agent speaks in the channel: play its audio when it appears.
  client.on("user-published", async (user, media) => {
    if (media !== "audio") return;
    await client.subscribe(user, "audio");
    user.audioTrack?.play?.();
  });
  await client.join(join.app_id, join.channel, join.token, join.uid);
  // Echo cancel, noise suppression, auto gain: the street is loud.
  const mic = await sdk.createMicrophoneAudioTrack({ AEC: true, ANS: true, AGC: true });
  await client.publish([mic]);
  return async () => {
    mic.stop();
    mic.close();
    await client.leave();
  };
}
