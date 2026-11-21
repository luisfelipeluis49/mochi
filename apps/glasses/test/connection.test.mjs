// The glasses client against the stand-in gateway, over a real WebSocket.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createConnection, STATUS } from '../lib/connection.js';
import { createMockSource } from '../lib/mock-source.js';
import { initialState, resetForNewConnection, parseEvent, reduce, socketUrl } from '../lib/protocol.js';
import { createMockBackend } from '../tools/mock-backend.mjs';

// A glasses client without the screen: connection + protocol, as the page wires them.
function createClient(base, userId, { glasses = true } = {}) {
  const client = { state: initialState(userId), statuses: [], events: [] };
  client.connection = createConnection({
    // A phone's Mobile view connects without `surface=ar`.
    url: glasses ? socketUrl(base, userId) : socketUrl(base, userId).replace('&surface=ar', ''),
    onStatus(status) {
      client.statuses.push(status);
      if (status === STATUS.ONLINE) client.state = resetForNewConnection(client.state);
    },
    onMessage(raw) {
      const event = parseEvent(raw);
      assert.ok(event, 'every frame from the gateway is an event');
      client.events.push(event);
      client.state = reduce(client.state, event, Date.now());
    },
  });
  return client;
}

async function until(condition, what, timeoutMs = 4000) {
  const deadline = Date.now() + timeoutMs;
  while (!condition()) {
    if (Date.now() > deadline) throw new Error(`timed out waiting for: ${what}`);
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}

function post(base, path, body) {
  return fetch(`${base}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  }).then((response) => response.json());
}

test('MOCK ONLY: the stand-in backend routes Ana\'s hint to Ana\'s connection and not Ben\'s (says nothing about the real gateway)', async () => {
  const backend = createMockBackend();
  const base = `http://localhost:${await backend.listen(0)}`;
  const ana = createClient(base, 'ana');
  const ben = createClient(base, 'ben');
  try {
    ana.connection.start();
    ben.connection.start();
    await until(() => ana.events.length === 2 && ben.events.length === 2, 'both get the session state on connect');
    assert.equal(ana.state.capturing, false);

    await post(base, '/api/sessions/demo/start');
    await until(() => ana.state.capturing && ben.state.capturing, 'listening after Start');

    const ordinary = await post(base, '/dev/sessions/demo/turn', { text: 'How was your day?' });
    assert.equal(ordinary.decision, 'IGNORE');

    await post(base, '/dev/sessions/demo/turn', { text: 'I need to adiar my meeting tomorrow.' });
    await until(() => ana.state.hint !== null, 'postpone on Ana\'s glasses');
    assert.deepEqual(ana.state.hint.candidates, [{ expression: 'postpone', meaning: 'adiar' }]);

    await post(base, '/dev/sessions/demo/turn', { text: 'I forgot my guarda-chuva at the office.' });
    await until(() => ana.state.hint.candidates[0].expression === 'umbrella', 'umbrella on Ana\'s glasses');

    await post(base, '/api/sessions/demo/stop');
    await until(() => !ana.state.capturing && !ben.state.capturing, 'not listening after Stop');

    assert.equal(ben.state.hint, null);
    // Snapshot (session + activity), then Start and Stop. No hint reached Ben.
    assert.deepEqual(ben.events.map((event) => event.type),
      ['session.state.changed', 'activity.state.changed', 'session.state.changed', 'session.state.changed']);
  } finally {
    ana.connection.stop();
    ben.connection.stop();
    await backend.close();
  }
});

test('MOCK ONLY: the stand-in gates candidate suggestions on surface=ar; the real gateway ignores surface (proposal, not in the contract)', async () => {
  const backend = createMockBackend();
  const base = `http://localhost:${await backend.listen(0)}`;
  const glasses = createClient(base, 'ana');
  const phone = createClient(base, 'ana', { glasses: false });
  const ben = createClient(base, 'ben');
  const everyone = [glasses, phone, ben];
  try {
    everyone.forEach((client) => client.connection.start());
    await until(() => everyone.every((client) => client.events.length === 2), 'all three connected');
    await post(base, '/api/sessions/demo/start');
    await until(() => everyone.every((client) => client.state.capturing), 'listening after Start');

    const decision = await post(base, '/dev/sessions/demo/turn', { text: 'I wanted to go, but...' });
    assert.equal(decision.decision, 'SHOW_HINT');
    await until(() => glasses.state.hint !== null, 'suggestions on the glasses');
    assert.equal(glasses.state.hint.context, 'I wanted to go, but…');
    assert.deepEqual(glasses.state.hint.candidates, [
      { expression: 'although', meaning: 'embora' },
      { expression: 'unfortunately', meaning: 'infelizmente' },
      { expression: 'instead', meaning: 'em vez disso' },
    ]);

    // A later event reaches everyone; by then a stray hint would have arrived too.
    await post(base, '/api/sessions/demo/stop');
    await until(() => everyone.every((client) => !client.state.capturing), 'not listening after Stop');
    assert.equal(phone.state.hint, null);
    assert.equal(ben.state.hint, null);
  } finally {
    everyone.forEach((client) => client.connection.stop());
    await backend.close();
  }
});

test('with the stand-in: the glasses reconnect by themselves and pick up the live hint', async () => {
  const backend = createMockBackend();
  const base = `http://localhost:${await backend.listen(0)}`;
  const ana = createClient(base, 'ana');
  try {
    ana.connection.start();
    await until(() => ana.statuses.includes(STATUS.ONLINE), 'first connection');
    await post(base, '/api/sessions/demo/start');
    await post(base, '/dev/sessions/demo/turn', { text: 'I need to adiar my meeting tomorrow.' });
    await until(() => ana.state.hint !== null, 'the hint');

    const before = ana.events.length;
    backend.dropConnections();
    await until(() => ana.statuses.includes(STATUS.RECONNECTING), 'notices the drop');
    await until(() => ana.statuses.at(-1) === STATUS.ONLINE && ana.events.length >= before + 3, 'back online with a snapshot');

    assert.equal(ana.state.capturing, true);
    assert.equal(ana.state.hint.candidates[0].expression, 'postpone');
  } finally {
    ana.connection.stop();
    await backend.close();
  }
});

test('stop() ends reconnecting for good', async () => {
  const statuses = [];
  // A port that was just free and is closed again: the connection is refused at once, on any machine.
  const { createServer } = await import('node:net');
  const probe = createServer();
  await new Promise((resolve) => probe.listen(0, '127.0.0.1', resolve));
  const { port } = probe.address();
  await new Promise((resolve) => probe.close(resolve));
  const connection = createConnection({
    url: `ws://127.0.0.1:${port}/ws?user=ana`,
    onStatus: (status) => statuses.push(status),
    onMessage: () => assert.fail('no message expected'),
  });
  connection.start();
  await until(() => statuses.includes(STATUS.RECONNECTING), 'first failure');
  connection.stop();
  const seen = statuses.length;
  await new Promise((resolve) => setTimeout(resolve, 1300)); // longer than the first retry wait
  assert.equal(statuses.length, seen);
});

test('demo mode (the replay source, no backend) produces contract events the protocol accepts', async () => {
  const frames = [];
  const statuses = [];
  const source = createMockSource({ onMessage: (raw) => frames.push(raw), onStatus: (status) => statuses.push(status) });
  source.start();
  try {
    await until(() => frames.length >= 2, 'session state and the first hint', 5000);
  } finally {
    source.stop();
  }
  assert.deepEqual(statuses, [STATUS.ONLINE]);
  let state = initialState('ana');
  for (const raw of frames) state = reduce(state, parseEvent(raw), Date.now());
  assert.equal(state.capturing, true);
  assert.equal(state.hint.context, 'I wanted to go, but…');
  assert.deepEqual(state.hint.candidates.map((candidate) => candidate.expression),
    ['although', 'unfortunately', 'instead']);
});

// --- Rejection, timeouts and backoff -------------------------------------

// A scripted WebSocket: the test decides when it opens, speaks and closes.
function fakeSockets() {
  const made = [];
  class FakeSocket {
    constructor(url) { this.url = url; this.closed = false; made.push(this); }
    close() { this.closed = true; }
  }
  return { made, FakeSocket };
}

const VALID = JSON.stringify({
  schema_version: '0.4', event_id: 'evt_1', type: 'session.state.changed', session_id: 'demo',
  emitted_at: '2026-11-19T16:00:00.000Z', sequence: 1,
  payload: { status: 'active', mode: 'together', focus: 'en', capturing: true, participants: ['ana', 'ben'] },
});

test('the backoff does not reset on open, only after a first valid event', async () => {
  const { made, FakeSocket } = fakeSockets();
  const statuses = [];
  const waits = [];
  const realSetTimeout = globalThis.setTimeout;
  globalThis.setTimeout = (fn, ms, ...rest) => { waits.push(ms); return realSetTimeout(fn, 0, ...rest); };
  const connection = createConnection({
    url: 'ws://x/ws?user=ana', WebSocketImpl: FakeSocket, connectTimeoutMs: 100000,
    onStatus: (status) => statuses.push(status), onMessage: () => {},
  });
  try {
    connection.start();
    for (let round = 0; round < 3; round += 1) {
      await until(() => made.length === round + 1, `socket ${round + 1}`);
      made[round].onopen();
      made[round].onclose({ code: 1006 }); // opened, then closed before any event
      await until(() => made.length === round + 2, 'retry');
    }
    assert.deepEqual(waits.filter((ms) => ms >= 1000 && ms < 100000), [1000, 2000, 5000]);
    assert.ok(!statuses.includes(STATUS.ONLINE), 'open alone is not online');

    made[3].onopen();
    made[3].onmessage({ data: VALID });
    assert.equal(statuses.at(-1), STATUS.ONLINE);
    made[3].onclose({ code: 1006 });
    await until(() => made.length === 5, 'retry after a good connection');
    assert.equal(waits.filter((ms) => ms >= 1000 && ms < 100000).at(-1), 1000, 'backoff restarted after a valid event');
  } finally {
    globalThis.setTimeout = realSetTimeout;
    connection.stop();
  }
});

test('close code 4400 stops retrying and reports the reason', async () => {
  const { made, FakeSocket } = fakeSockets();
  const calls = [];
  const connection = createConnection({
    url: 'ws://x/ws?user=sophie', WebSocketImpl: FakeSocket,
    onStatus: (status, detail) => calls.push([status, detail]), onMessage: () => {},
  });
  connection.start();
  made[0].onopen();
  made[0].onclose({ code: 4400, reason: 'unknown user' });
  assert.deepEqual(calls.at(-1), [STATUS.REJECTED, 'unknown user']);
  await new Promise((resolve) => setTimeout(resolve, 1300));
  assert.equal(made.length, 1, 'no second attempt');
  connection.stop();
});

test('against the stand-in backend: an unknown user is accepted then closed with 4400, and not retried', async () => {
  const backend = createMockBackend();
  const base = `http://localhost:${await backend.listen(0)}`;
  const calls = [];
  const connection = createConnection({
    url: socketUrl(base, 'sophie'),
    onStatus: (status, detail) => calls.push([status, detail]), onMessage: () => assert.fail('no event for a rejected user'),
  });
  try {
    connection.start();
    await until(() => calls.some(([status]) => status === STATUS.REJECTED), 'rejected');
    const rejected = calls.find(([status]) => status === STATUS.REJECTED);
    assert.match(rejected[1], /sophie/);
    await new Promise((resolve) => setTimeout(resolve, 1300));
    assert.equal(calls.filter(([status]) => status === STATUS.RECONNECTING).length, 0);
    assert.ok(!calls.some(([status]) => status === STATUS.ONLINE));
  } finally {
    connection.stop();
    await backend.close();
  }
});

test('a socket that never opens is closed after the connect timeout and retried as WAKING_UP', async () => {
  const { made, FakeSocket } = fakeSockets();
  const statuses = [];
  const connection = createConnection({
    url: 'ws://x/ws?user=ana', WebSocketImpl: FakeSocket, connectTimeoutMs: 30,
    onStatus: (status) => statuses.push(status), onMessage: () => {},
  });
  try {
    connection.start();
    await until(() => made[0].closed, 'first socket closed by the timeout');
    assert.equal(statuses.at(-1), STATUS.WAKING_UP);
    await until(() => made.length === 2, 'retry');
  } finally {
    connection.stop();
  }
});

test('the connect timer is cancelled when the socket opens', async () => {
  const { made, FakeSocket } = fakeSockets();
  const connection = createConnection({
    url: 'ws://x/ws?user=ana', WebSocketImpl: FakeSocket, connectTimeoutMs: 30,
    onStatus: () => {}, onMessage: () => {},
  });
  try {
    connection.start();
    made[0].onopen();
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(made[0].closed, false);
  } finally {
    connection.stop();
  }
});

test('the stand-in replaces a hint with hint.cleared and clears it at expiry', async () => {
  const backend = createMockBackend({ hintMs: 150 });
  const base = `http://localhost:${await backend.listen(0)}`;
  const ana = createClient(base, 'ana');
  try {
    ana.connection.start();
    await until(() => ana.events.length === 2, 'snapshot');
    await post(base, '/dev/sessions/demo/turn', { text: 'adiar' });
    await post(base, '/dev/sessions/demo/turn', { text: 'guarda-chuva' });
    await until(() => ana.events.filter((e) => e.type === 'hint.cleared').length >= 2, 'cleared on replace and at expiry');
    const types = ana.events.map((e) => e.type).slice(2);
    assert.deepEqual(types.slice(0, 3), ['hint.created', 'hint.cleared', 'hint.created']);
    assert.equal(ana.state.hint, null);
  } finally {
    ana.connection.stop();
    await backend.close();
  }
});

test('a socket that fails with only an error event (no close) is retried', async () => {
  // Node 22's WebSocket behaves this way when the connection is refused.
  const statuses = [];
  const sockets = [];
  class ErrorOnlySocket {
    constructor() {
      this.readyState = 0;
      sockets.push(this);
      setTimeout(() => this.onerror && this.onerror({}), 5);
    }
    close() {}
  }
  const connection = createConnection({
    url: 'ws://127.0.0.1:1/ws?user=ana',
    WebSocketImpl: ErrorOnlySocket,
    onStatus: (status) => statuses.push(status),
    onMessage: () => assert.fail('no message expected'),
  });
  connection.start();
  try {
    await until(() => statuses.includes(STATUS.RECONNECTING), 'the retry after an error without close');
    await until(() => sockets.length >= 2, 'a second attempt', 3000);
  } finally {
    connection.stop();
  }
});
