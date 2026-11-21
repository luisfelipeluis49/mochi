// The glasses client against the stand-in gateway, over a real WebSocket.
import test from 'node:test';
import assert from 'node:assert/strict';
import { createConnection, STATUS } from '../lib/connection.js';
import { createMockSource } from '../lib/mock-source.js';
import { initialState, resetForNewConnection, parseEvent, reduce, socketUrl } from '../lib/protocol.js';
import { createMockBackend } from '../tools/mock-backend.mjs';

// A glasses client without the screen: connection + protocol, as the page wires them.
function createClient(base, userId, { glasses = true } = {}) {
  const client = { state: initialState(), statuses: [], events: [] };
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

test('a hint for Ana reaches her glasses and not Ben\'s', async () => {
  const backend = createMockBackend();
  const base = `http://localhost:${await backend.listen(0)}`;
  const ana = createClient(base, 'ana');
  const ben = createClient(base, 'ben');
  try {
    ana.connection.start();
    ben.connection.start();
    await until(() => ana.events.length === 1 && ben.events.length === 1, 'both get the session state on connect');
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
    assert.deepEqual(ben.events.map((event) => event.type),
      ['session.state.changed', 'session.state.changed', 'session.state.changed']);
  } finally {
    ana.connection.stop();
    ben.connection.stop();
    await backend.close();
  }
});

test('predictive suggestions reach Ana\'s glasses only: not her phone, not Ben', async () => {
  const backend = createMockBackend();
  const base = `http://localhost:${await backend.listen(0)}`;
  const glasses = createClient(base, 'ana');
  const phone = createClient(base, 'ana', { glasses: false });
  const ben = createClient(base, 'ben');
  const everyone = [glasses, phone, ben];
  try {
    everyone.forEach((client) => client.connection.start());
    await until(() => everyone.every((client) => client.events.length === 1), 'all three connected');
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

test('the glasses reconnect by themselves and pick up the live hint', async () => {
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
    await until(() => ana.statuses.at(-1) === STATUS.ONLINE && ana.events.length >= before + 2, 'back online with a snapshot');

    assert.equal(ana.state.capturing, true);
    assert.equal(ana.state.hint.candidates[0].expression, 'postpone');
  } finally {
    ana.connection.stop();
    await backend.close();
  }
});

test('stop() ends reconnecting for good', async () => {
  const statuses = [];
  // Nothing listens on this port.
  const connection = createConnection({
    url: 'ws://127.0.0.1:9/ws?user=ana',
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

test('demo mode produces contract events the protocol accepts', async () => {
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
  let state = initialState();
  for (const raw of frames) state = reduce(state, parseEvent(raw), Date.now());
  assert.equal(state.capturing, true);
  assert.equal(state.hint.context, 'I wanted to go, but…');
  assert.deepEqual(state.hint.candidates.map((candidate) => candidate.expression),
    ['although', 'unfortunately', 'instead']);
});
