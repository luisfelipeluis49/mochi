import { test } from "node:test";
import assert from "node:assert/strict";
import { VoiceError, clampVolume, joinVoice, type AgoraClient, type AgoraSdk, type RemoteUser } from "./agora.ts";
import { flush } from "./testkit.ts";

const join = { app_id: "app", channel: "mochi-demo-w-00000000", uid: 7, token: "tok" };

function fakeSdk(fail: { join?: boolean; mic?: unknown; publish?: boolean } = {}) {
  const log: string[] = [];
  const handlers: Record<string, (u: RemoteUser, m: "audio" | "video") => void> = {};
  let remoteVolume = -1;
  const client: AgoraClient = {
    join: async (...a) => { log.push(`join ${a.join(",")}`); if (fail.join) throw new Error("join"); },
    publish: async () => { log.push("publish"); if (fail.publish) throw new Error("publish"); },
    subscribe: async () => { log.push("subscribe"); },
    on: (ev: string, cb: (u: RemoteUser, m: "audio" | "video") => void) => { handlers[ev] = cb; },
    leave: async () => { log.push("leave"); },
  };
  const sdk: AgoraSdk = {
    createClient: () => client,
    createMicrophoneAudioTrack: async (c) => {
      log.push(`mic ${JSON.stringify(c)}`);
      if (fail.mic) throw fail.mic;
      return { getVolumeLevel: () => 0.3, stop: () => log.push("mic stop"), close: () => log.push("mic close") };
    },
  };
  const remote: RemoteUser = {
    audioTrack: { play: () => log.push("play"), stop: () => log.push("remote stop"), setVolume: (v) => { remoteVolume = v; }, getVolumeLevel: () => 0.5 },
  };
  return { sdk, log, handlers, remote, remoteVolume: () => remoteVolume };
}

test("joins with the uid, publishes the mic with AEC/ANS/AGC, plays Mochi and leaves", async () => {
  const f = fakeSdk();
  const link = await joinVoice(join, { volume: 80, sdk: async () => f.sdk });
  assert.deepEqual(f.log.slice(0, 3), ["join app,mochi-demo-w-00000000,tok,7", 'mic {"AEC":true,"ANS":true,"AGC":true}', "publish"]);
  assert.equal(link.micLevel(), 0.3);
  assert.equal(link.remoteLevel(), null);
  f.handlers["user-published"](f.remote, "audio");
  await flush();
  assert.equal(f.remoteVolume(), 80);
  assert.equal(link.remoteLevel(), 0.5);
  link.setVolume(30);
  assert.equal(f.remoteVolume(), 30);
  await link.leave();
  await link.leave();
  assert.equal(f.log.filter((l) => l === "leave").length, 1);
  assert.ok(f.log.includes("mic stop") && f.log.includes("mic close"));
});

test("an SDK that does not load is agora_sdk", async () => {
  await assert.rejects(joinVoice(join, { volume: 80, sdk: async () => { throw new Error("blocked"); } }),
    (e: unknown) => e instanceof VoiceError && e.failure.kind === "agora_sdk");
});

test("a refused join is agora_join", async () => {
  const f = fakeSdk({ join: true });
  await assert.rejects(joinVoice(join, { volume: 80, sdk: async () => f.sdk }), (e: unknown) => e instanceof VoiceError && e.failure.kind === "agora_join");
});

test("a microphone error carries its problem and leaves the channel", async () => {
  const f = fakeSdk({ mic: Object.assign(new Error("x"), { name: "AgoraRTCException", code: "PERMISSION_DENIED" }) });
  await assert.rejects(joinVoice(join, { volume: 80, sdk: async () => f.sdk }),
    (e: unknown) => e instanceof VoiceError && e.failure.kind === "mic" && e.failure.problem === "denied");
  assert.ok(f.log.includes("leave"));
});

test("a failed publish closes the mic and is agora_join", async () => {
  const f = fakeSdk({ publish: true });
  await assert.rejects(joinVoice(join, { volume: 80, sdk: async () => f.sdk }), (e: unknown) => e instanceof VoiceError && e.failure.kind === "agora_join");
  assert.ok(f.log.includes("mic close") && f.log.includes("leave"));
});

test("volume is clamped to 0..100", () => {
  assert.equal(clampVolume(120), 100);
  assert.equal(clampVolume(-3), 0);
  assert.equal(clampVolume(NaN), 80);
  assert.equal(clampVolume(42.4), 42);
});
