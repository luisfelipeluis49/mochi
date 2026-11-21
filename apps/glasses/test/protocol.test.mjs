import test from 'node:test';
import assert from 'node:assert/strict';
import {
  initialState, resetForNewConnection, parseEvent, reduce, expire, dismiss,
  hintLifetimeMs, socketUrl, candidatesOf, contextLine,
  DEFAULT_HINT_MS, MAX_HINT_MS, MAX_CONTEXT_CHARS,
} from '../lib/protocol.js';

const T0 = Date.parse('2026-11-19T16:00:04.700Z');

function envelope(type, payload, sequence, emittedAt = '2026-11-19T16:00:04.700Z') {
  return {
    schema_version: '0.4', event_id: `evt_${sequence}`, type, session_id: 'demo',
    emitted_at: emittedAt, sequence, payload,
  };
}

// The Hint example from the contract, section 6.2.
const POSTPONE = {
  hint_id: 'hint_015', target_user_id: 'ana', target_language: 'en',
  expression: 'postpone', meaning: 'adiar', example: 'I need to postpone my meeting.',
  reason: 'code_switch', expires_at: '2026-11-19T16:00:12.700Z',
};

// The same Hint with the two proposed Fluency Helper fields (vision, 10.3).
const BUT = {
  ...POSTPONE, hint_id: 'hint_101', expression: 'although', meaning: 'embora', example: null,
  reason: 'trails_off', context: 'I wanted to go, but',
  candidates: [
    { expression: 'although', meaning: 'embora' },
    { expression: 'unfortunately', meaning: 'infelizmente' },
    { expression: 'instead', meaning: 'em vez disso' },
  ],
};

const SESSION_ACTIVE = {
  status: 'active', mode: 'together', focus: 'en', capturing: true, participants: ['ana', 'ben'],
};

test('parseEvent accepts a contract envelope and rejects everything else', () => {
  const raw = JSON.stringify(envelope('hint.created', POSTPONE, 42));
  assert.equal(parseEvent(raw).payload.expression, 'postpone');
  assert.equal(parseEvent('not json'), null);
  assert.equal(parseEvent('[]'), null);
  assert.equal(parseEvent('{"type":"hint.created","payload":{}}'), null); // no sequence
  assert.equal(parseEvent('{"type":"hint.created","sequence":1}'), null); // no payload
  assert.equal(parseEvent(new ArrayBuffer(4)), null);
});

test('session.state.changed turns listening on and off', () => {
  let state = reduce(initialState('ana'), envelope('session.state.changed', SESSION_ACTIVE, 1), T0);
  assert.equal(state.capturing, true);
  state = reduce(state, envelope('session.state.changed', { ...SESSION_ACTIVE, capturing: false }, 2), T0);
  assert.equal(state.capturing, false);
});

test('a v0.4 hint shows its one word and meaning for 8 seconds', () => {
  const state = reduce(initialState('ana'), envelope('hint.created', POSTPONE, 1), T0);
  assert.deepEqual(state.hint, {
    hintId: 'hint_015', context: '',
    candidates: [{ expression: 'postpone', meaning: 'adiar' }],
    hideAtMs: T0 + 8000,
  });
  assert.equal(expire(state, T0 + 7999), state);
  assert.equal(expire(state, T0 + 8000).hint, null);
});

test('a hint with candidates shows up to three of them, with the context', () => {
  const state = reduce(initialState('ana'), envelope('hint.created', BUT, 1), T0);
  assert.equal(state.hint.context, 'I wanted to go, but…');
  assert.deepEqual(state.hint.candidates, [
    { expression: 'although', meaning: 'embora' },
    { expression: 'unfortunately', meaning: 'infelizmente' },
    { expression: 'instead', meaning: 'em vez disso' },
  ]);
});

test('candidates: at most three, no repeats, unusable entries skipped', () => {
  const payload = {
    expression: 'ignored', meaning: 'x',
    candidates: [
      { expression: ' although ', meaning: ' embora ' },
      { expression: 'Although', meaning: 'again' },
      null, 'text', { meaning: 'no expression' }, { expression: '   ' },
      { expression: 'instead' },
      { expression: 'however', meaning: 'porém' },
      { expression: 'yet', meaning: 'ainda' },
    ],
  };
  assert.deepEqual(candidatesOf(payload), [
    { expression: 'although', meaning: 'embora' },
    { expression: 'instead', meaning: '' },
    { expression: 'however', meaning: 'porém' },
  ]);
});

test('candidates: an empty or unusable list falls back to the single expression', () => {
  for (const candidates of [undefined, null, [], [null, { meaning: 'x' }], 'although']) {
    assert.deepEqual(candidatesOf({ expression: 'postpone', meaning: 'adiar', candidates }),
      [{ expression: 'postpone', meaning: 'adiar' }]);
  }
});

test('context: short ones get an ellipsis, long ones keep their end', () => {
  assert.equal(contextLine('I wanted to go, but'), 'I wanted to go, but…');
  assert.equal(contextLine('  I wanted to go, but...  '), 'I wanted to go, but…');
  assert.equal(contextLine(''), '');
  assert.equal(contextLine(null), '');
  const long = contextLine('Yesterday I went to the supermarket because I needed to buy some fruit and then I');
  assert.ok(long.startsWith('…') && long.endsWith('and then I…'), long);
  assert.ok(long.length <= MAX_CONTEXT_CHARS + 2, long);
  assert.ok(!long.startsWith('… '), 'cut at a word, not mid-space');
});

test('a hint with no meaning or no target is still shown', () => {
  const payload = { ...POSTPONE, meaning: null, example: null, target_user_id: null };
  const state = reduce(initialState('ana'), envelope('hint.created', payload, 1), T0);
  assert.deepEqual(state.hint.candidates, [{ expression: 'postpone', meaning: '' }]);
});

test('a hint without a usable word, or without an id, is not shown', () => {
  for (const expression of [undefined, null, '', '   ', 7]) {
    const state = reduce(initialState('ana'), envelope('hint.created', { ...POSTPONE, expression }, 1), T0);
    assert.equal(state.hint, null);
  }
  for (const hint_id of [undefined, null, '', 9]) {
    const state = reduce(initialState('ana'), envelope('hint.created', { ...BUT, hint_id }, 1), T0);
    assert.equal(state.hint, null);
  }
});

test('an event whose sequence was already applied is ignored', () => {
  const first = reduce(initialState('ana'), envelope('hint.created', POSTPONE, 5), T0);
  const cleared = reduce(first, envelope('hint.cleared', { hint_id: 'hint_015' }, 6), T0);
  assert.equal(cleared.hint, null);
  // The old hint.created arrives again: it must not bring the word back.
  assert.equal(reduce(cleared, envelope('hint.created', POSTPONE, 5), T0), cleared);
});

test('a new connection starts sequence tracking again', () => {
  const state = reduce(initialState('ana'), envelope('session.state.changed', SESSION_ACTIVE, 900), T0);
  const fresh = resetForNewConnection(state);
  const next = reduce(fresh, envelope('hint.created', POSTPONE, 1), T0);
  assert.equal(next.hint.candidates[0].expression, 'postpone');
});

test('hint.cleared removes only the hint it names', () => {
  const shown = reduce(initialState('ana'), envelope('hint.created', POSTPONE, 1), T0);
  assert.equal(reduce(shown, envelope('hint.cleared', { hint_id: 'hint_999' }, 2), T0).hint.hintId, 'hint_015');
  assert.equal(reduce(shown, envelope('hint.cleared', { hint_id: 'hint_015' }, 2), T0).hint, null);
});

test('a newer hint replaces the one on screen', () => {
  let state = reduce(initialState('ana'), envelope('hint.created', POSTPONE, 1), T0);
  state = reduce(state, envelope('hint.created', BUT, 2), T0);
  assert.equal(state.hint.hintId, 'hint_101');
  assert.equal(state.hint.candidates.length, 3);
});

test('events for other screens change nothing visible', () => {
  const before = reduce(initialState('ana'), envelope('hint.created', POSTPONE, 1), T0);
  for (const type of ['activity.state.changed', 'learning_event.created', 'agent.speak.requested', 'something.new']) {
    const after = reduce(before, envelope(type, { anything: true }, 2), T0);
    assert.deepEqual(after.hint, before.hint);
    assert.equal(after.capturing, before.capturing);
  }
});

test('dismiss puts the word away and is a no-op with nothing shown', () => {
  const shown = reduce(initialState('ana'), envelope('hint.created', POSTPONE, 1), T0);
  assert.equal(dismiss(shown).hint, null);
  const empty = initialState('ana');
  assert.equal(dismiss(empty), empty);
});

test('hint lifetime: device clock in step with the server', () => {
  const event = envelope('hint.created', POSTPONE, 1);
  assert.equal(hintLifetimeMs(event, T0), 8000);
  assert.equal(hintLifetimeMs(event, T0 + 150), 7850); // network delay
});

test('hint lifetime: a live hint replayed on reconnect keeps only its remaining time', () => {
  const event = envelope('hint.created', POSTPONE, 1); // emitted at T0, original envelope
  assert.equal(hintLifetimeMs(event, T0 + 5000), 3000);
});

test('hint lifetime: a wrong device clock falls back to the length the server gave', () => {
  const event = envelope('hint.created', POSTPONE, 1);
  assert.equal(hintLifetimeMs(event, T0 + 60 * 60 * 1000), 8000); // device an hour ahead
  assert.equal(hintLifetimeMs(event, T0 - 60 * 60 * 1000), 8000); // device an hour behind
});

test('hint lifetime: missing or broken times fall back to the default, and are capped', () => {
  assert.equal(hintLifetimeMs(envelope('hint.created', { ...POSTPONE, expires_at: null }, 1), T0), DEFAULT_HINT_MS);
  assert.equal(hintLifetimeMs(envelope('hint.created', { ...POSTPONE, expires_at: 'soon' }, 1), T0), DEFAULT_HINT_MS);
  assert.equal(hintLifetimeMs(envelope('hint.created', POSTPONE, 1, null), T0), 8000);
  const farFuture = { ...POSTPONE, expires_at: '2027-01-01T00:00:00.000Z' };
  assert.equal(hintLifetimeMs(envelope('hint.created', farFuture, 1), T0), MAX_HINT_MS);
});

test('socketUrl builds one person\'s address and says these are glasses', () => {
  assert.equal(socketUrl('https://mochi.example.com', 'ana'), 'wss://mochi.example.com/ws?user=ana&surface=ar');
  assert.equal(socketUrl('http://192.168.1.20:8787/', 'ben'), 'ws://192.168.1.20:8787/ws?user=ben&surface=ar');
  assert.equal(socketUrl('wss://mochi.example.com', 'ana'), 'wss://mochi.example.com/ws?user=ana&surface=ar');
  assert.equal(socketUrl('', 'ana'), '');
  assert.equal(socketUrl(undefined, 'ana'), '');
});

test('a hint for another person is ignored, one for the wearer or for nobody is shown', () => {
  const forBen = { ...POSTPONE, hint_id: 'hint_200', target_user_id: 'ben' };
  const forNobody = { ...POSTPONE, hint_id: 'hint_201', target_user_id: null };
  let state = reduce(initialState('ana'), envelope('hint.created', forBen, 1), T0);
  assert.equal(state.hint, null, "Ben's hint is not shown on Ana's glasses");
  state = reduce(state, envelope('hint.created', forNobody, 2), T0);
  assert.equal(state.hint.hintId, 'hint_201');
  state = reduce(state, envelope('hint.created', { ...forBen, hint_id: 'hint_202' }, 3), T0);
  assert.equal(state.hint.hintId, 'hint_201', "Ben's later hint does not replace what Ana sees");
  state = reduce(initialState('ben'), envelope('hint.created', forBen, 1), T0);
  assert.equal(state.hint.hintId, 'hint_200');
});

test('with no known wearer, only hints for nobody are shown', () => {
  assert.equal(reduce(initialState(), envelope('hint.created', POSTPONE, 1), T0).hint, null);
  const forNobody = { ...POSTPONE, target_user_id: null };
  assert.notEqual(reduce(initialState(), envelope('hint.created', forNobody, 1), T0).hint, null);
});

test('expression with " · " holds up to three options, the meaning shown once', () => {
  const payload = { ...POSTPONE, expression: 'postpone · delay · put off · reschedule', meaning: 'adiar' };
  assert.deepEqual(candidatesOf(payload), [
    { expression: 'postpone', meaning: 'adiar' },
    { expression: 'delay', meaning: '' },
    { expression: 'put off', meaning: '' },
  ]);
  assert.deepEqual(candidatesOf({ ...POSTPONE, expression: 'although · although' }),
    [{ expression: 'although', meaning: 'adiar' }]);
});

test('candidates still win over a " · " expression', () => {
  const payload = { ...BUT, expression: 'a · b' };
  assert.deepEqual(candidatesOf(payload).map((c) => c.expression), ['although', 'unfortunately', 'instead']);
});

test('socketUrl refuses an address without a scheme, with a clear error', () => {
  assert.throws(() => socketUrl('mochi.example.com', 'ana'), /http\(s\):\/\/ or ws\(s\):\/\//);
  assert.throws(() => socketUrl('localhost:8787', 'ana'), /scheme/i);
  assert.throws(() => socketUrl('ftp://mochi.example.com', 'ana'), /scheme/i);
});
