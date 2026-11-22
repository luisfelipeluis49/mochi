import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LOST_USER_CODE, backoffMs, connectSocket, parseEvent, socketUrl, type SocketLike } from "./socket.ts";
import { fakeTimers } from "./testkit.ts";

class FakeSocket implements SocketLike {
  static all: FakeSocket[] = [];
  onopen: SocketLike["onopen"] = null;
  onmessage: SocketLike["onmessage"] = null;
  onclose: SocketLike["onclose"] = null;
  onerror: SocketLike["onerror"] = null;
  closed = false;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeSocket.all.push(this);
  }
  close() {
    this.closed = true;
  }
}

test("the URL matches the page protocol and carries user and session", () => {
  assert.equal(socketUrl({ protocol: "http:", host: "localhost:5173" }, "ana", "w-3f9c1a2b"), "ws://localhost:5173/ws?user=ana&session=w-3f9c1a2b");
  assert.equal(socketUrl({ protocol: "https:", host: "mochi.example" }, "luis-felipe-3f9c1a", "w-00000000"), "wss://mochi.example/ws?user=luis-felipe-3f9c1a&session=w-00000000");
});

test("the backoff runs 1, 2, 4, 8, 15, 15 seconds", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 9].map(backoffMs), [1000, 2000, 4000, 8000, 15000, 15000, 15000]);
});

test("reconnects on the schedule and resets after a good open", () => {
  FakeSocket.all = [];
  const timers = fakeTimers();
  const closes: (number | null)[] = [];
  let opens = 0;
  connectSocket("ws://x/ws", {
    onOpen: () => opens++, onEvent: () => {}, onClose: (i) => closes.push(i.retryInMs), onLostUser: () => assert.fail("not lost"),
  }, { WebSocket: FakeSocket, timers });
  assert.equal(FakeSocket.all.length, 1);
  for (let i = 0; i < 6; i++) {
    const s = FakeSocket.all[FakeSocket.all.length - 1];
    s.onclose?.({ code: 1006, reason: "" });
    timers.tick(closes[closes.length - 1]!);
  }
  assert.deepEqual(closes, [1000, 2000, 4000, 8000, 15000, 15000]);
  assert.equal(FakeSocket.all.length, 7);
  const last = FakeSocket.all[6];
  last.onopen?.({});
  assert.equal(opens, 1);
  last.onclose?.({ code: 1006, reason: "" });
  assert.equal(closes[closes.length - 1], 1000);
});

test("close code 4400 stops reconnecting and reports the lost user", () => {
  FakeSocket.all = [];
  const timers = fakeTimers();
  let lost = 0;
  const closes: (number | null)[] = [];
  connectSocket("ws://x/ws", { onOpen() {}, onEvent() {}, onClose: (i) => closes.push(i.retryInMs), onLostUser: () => lost++ }, { WebSocket: FakeSocket, timers });
  FakeSocket.all[0].onclose?.({ code: LOST_USER_CODE, reason: "unknown user" });
  timers.tick(60_000);
  assert.equal(lost, 1);
  assert.deepEqual(closes, [null]);
  assert.equal(FakeSocket.all.length, 1);
});

test("close() by the app stops everything", () => {
  FakeSocket.all = [];
  const timers = fakeTimers();
  const c = connectSocket("ws://x/ws", { onOpen() {}, onEvent() {}, onClose: () => assert.fail("no close report"), onLostUser() {} }, { WebSocket: FakeSocket, timers });
  c.close();
  assert.equal(FakeSocket.all[0].closed, true);
  FakeSocket.all[0].onclose?.({ code: 1000, reason: "" });
  timers.tick(60_000);
  assert.equal(FakeSocket.all.length, 1);
});

test("messages become events; junk is ignored", () => {
  FakeSocket.all = [];
  const got: string[] = [];
  connectSocket("ws://x/ws", { onOpen() {}, onEvent: (e) => got.push(e.type), onClose() {}, onLostUser() {} }, { WebSocket: FakeSocket, timers: fakeTimers() });
  const ex = readFileSync(new URL("../../../../packages/contracts/examples/events/hint.created.json", import.meta.url), "utf8");
  FakeSocket.all[0].onmessage?.({ data: ex });
  FakeSocket.all[0].onmessage?.({ data: "{oops" });
  FakeSocket.all[0].onmessage?.({ data: JSON.stringify({ type: "weird.event", sequence: 1, payload: {} }) });
  assert.deepEqual(got, ["hint.created"]);
  assert.equal(parseEvent(42), null);
});
