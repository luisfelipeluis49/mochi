// A stand-in for the Mochi gateway, for developing the glasses app without the
// real backend (services/backend). It is NOT the backend: it knows two words and one
// hesitation, and nothing else. It follows the team contract (draft v0.4,
// section 6) for the parts the glasses touch (snapshot on connect: session and
// activity state; hint.cleared on replace and expiry; 4400 for an unknown user), plus the two things the glasses
// PROPOSE for the Fluency Helper: `&surface=ar` on the connection, and
// `candidates` / `context` on the Hint.
//
//   GET  /ws?user=ana[&surface=ar] | ?device=home_pi_01 | ?view=audience
//   POST /api/sessions/demo/start | /stop
//   POST /dev/sessions/demo/turn   { "text": "..." }
//   POST /api/demo/reset
//
// Run:  npm run mock-backend            (port 8787, or PORT=...)
// Say:  curl -X POST localhost:8787/dev/sessions/demo/turn \
//         -H 'content-type: application/json' \
//         -d '{"text":"I need to adiar my meeting tomorrow"}'

import http from 'node:http';
import { pathToFileURL } from 'node:url';
import { WebSocketServer } from 'ws';

const HINT_MS = 8000;
const USERS = ['ana', 'ben']; // the real roster; anyone else is accepted, then closed with 4400

// The M0 "one-rule decide()", plus the second demo sentence.
const WORDS = [
  { heard: 'adiar', expression: 'postpone', meaning: 'adiar', example: 'I need to postpone my meeting.' },
  { heard: 'guarda-chuva', expression: 'umbrella', meaning: 'guarda-chuva', example: 'I forgot my umbrella at the office.' },
];

// One hesitation, answered with predictive suggestions (the vision's example,
// with meanings for Ana). These go to glasses only.
const HESITATIONS = [
  {
    heard: 'i wanted to go, but',
    context: 'I wanted to go, but',
    candidates: [
      { expression: 'although', meaning: 'embora' },
      { expression: 'unfortunately', meaning: 'infelizmente' },
      { expression: 'instead', meaning: 'em vez disso' },
    ],
  },
];

export function createMockBackend({ hintMs = HINT_MS } = {}) {
  const clients = new Set(); // { socket, kind: 'user' | 'home' | 'audience', userId, surface }
  let sequence = 0;
  let hintCount = 0;
  let session = newSession();
  let liveHint = null; // { payload, expiresMs }

  function newSession() {
    return { status: 'created', mode: 'together', focus: 'en', capturing: false, participants: ['ana', 'ben'] };
  }

  function envelope(type, payload) {
    sequence += 1;
    return JSON.stringify({
      schema_version: '0.4',
      event_id: `evt_${String(sequence).padStart(3, '0')}`,
      type,
      session_id: 'demo',
      emitted_at: new Date().toISOString(),
      sequence,
      payload,
    });
  }

  // Contract 6.2: a hint goes to the Home view, the Audience view, and the
  // target user's Mobile view. A hint with no target goes to everyone.
  function hintGoesTo(client, hint) {
    if (client.kind !== 'user') return true;
    return hint.target_user_id === null || hint.target_user_id === client.userId;
  }

  // Proposed: predictive suggestions are AR-exclusive, so they go only to the
  // target person's glasses, not to Home, the projector or their phone.
  function suggestionGoesTo(client, hint) {
    return client.kind === 'user' && client.surface === 'ar' && hintGoesTo(client, hint);
  }

  function publish(type, payload, accepts = () => true) {
    const frame = envelope(type, payload);
    for (const client of clients) {
      if (accepts(client) && client.socket.readyState === 1) client.socket.send(frame);
    }
  }

  const IDLE_ACTIVITY = {
    activity_id: 'describe_and_guess', round_id: null, state: 'IDLE', describer_user_id: null,
    guesser_user_id: null, public_instruction: null, result: null, revealed_word: null, word_source: null,
  };
  let expiryTimer = null;

  // Like the real gateway: a hint ends with hint.cleared, whether a newer hint
  // replaced it or its time ran out. The clear goes to whoever got the hint.
  function clearLiveHint() {
    if (expiryTimer !== null) {
      clearTimeout(expiryTimer);
      expiryTimer = null;
    }
    if (!liveHint) return;
    const { payload, accepts } = liveHint;
    liveHint = null;
    publish('hint.cleared', { hint_id: payload.hint_id }, (client) => accepts(client, payload));
  }

  function publishSession() {
    publish('session.state.changed', session);
  }

  function handleTurn(text) {
    const lower = String(text || '').toLowerCase();
    const word = WORDS.find((entry) => lower.includes(entry.heard));
    const hesitation = word ? null : HESITATIONS.find((entry) => lower.includes(entry.heard));
    if (!word && !hesitation) return { decision: 'IGNORE' };
    hintCount += 1;
    clearLiveHint();
    const expiresMs = Date.now() + hintMs;
    const first = word || hesitation.candidates[0];
    const payload = {
      hint_id: `hint_${String(hintCount).padStart(3, '0')}`,
      target_user_id: 'ana',
      target_language: 'en',
      expression: first.expression,
      meaning: first.meaning,
      example: word ? word.example : null,
      reason: word ? 'code_switch' : 'trails_off',
      expires_at: new Date(expiresMs).toISOString(),
    };
    if (hesitation) {
      payload.context = hesitation.context;
      payload.candidates = hesitation.candidates;
    }
    const accepts = hesitation ? suggestionGoesTo : hintGoesTo;
    liveHint = { payload, expiresMs, accepts };
    expiryTimer = setTimeout(() => {
      expiryTimer = null;
      clearLiveHint();
    }, hintMs);
    expiryTimer.unref();
    publish('hint.created', payload, (client) => accepts(client, payload));
    return { decision: 'SHOW_HINT', hint: payload };
  }

  function readJson(request) {
    return new Promise((resolve) => {
      let body = '';
      request.on('data', (chunk) => { body += chunk; });
      request.on('end', () => {
        try { resolve(body ? JSON.parse(body) : {}); } catch { resolve(null); }
      });
    });
  }

  function reply(response, status, body) {
    response.writeHead(status, { 'content-type': 'application/json' });
    response.end(JSON.stringify(body));
  }

  const server = http.createServer(async (request, response) => {
    const { pathname } = new URL(request.url, 'http://localhost');
    if (request.method !== 'POST') return reply(response, 404, { error: 'not found' });

    if (pathname === '/api/sessions/demo/start') {
      session = { ...session, status: 'active', capturing: true };
      publishSession();
      return reply(response, 200, session);
    }
    if (pathname === '/api/sessions/demo/stop') {
      session = { ...session, status: 'ended', capturing: false };
      publishSession();
      return reply(response, 200, session);
    }
    if (pathname === '/api/demo/reset') {
      session = newSession();
      clearLiveHint();
      publishSession();
      return reply(response, 200, session);
    }
    if (pathname === '/dev/sessions/demo/turn') {
      const body = await readJson(request);
      if (!body || typeof body.text !== 'string') return reply(response, 400, { error: 'expected { "text": "..." }' });
      return reply(response, 200, handleTurn(body.text));
    }
    return reply(response, 404, { error: 'not found' });
  });

  const sockets = new WebSocketServer({ noServer: true });

  server.on('upgrade', (request, socket, head) => {
    const url = new URL(request.url, 'http://localhost');
    const user = url.searchParams.get('user');
    let client = null;
    if (url.pathname === '/ws') {
      if (user) client = { kind: 'user', userId: user, surface: url.searchParams.get('surface') };
      else if (url.searchParams.get('device')) client = { kind: 'home', userId: null };
      else if (url.searchParams.get('view') === 'audience') client = { kind: 'audience', userId: null };
    }
    if (!client) {
      socket.destroy();
      return;
    }
    sockets.handleUpgrade(request, socket, head, (ws) => {
      client.socket = ws;
      clients.add(client);
      ws.on('close', () => clients.delete(client));
      ws.on('error', () => clients.delete(client));
      // On connect: the current session state and any live hint.
      if (client.kind === 'user' && !USERS.includes(client.userId)) {
        // The real backend accepts, then closes: 4400 with a reason.
        ws.close(4400, `unknown user: ${client.userId}`);
        return;
      }
      ws.send(envelope('session.state.changed', session));
      ws.send(envelope('activity.state.changed', IDLE_ACTIVITY));
      if (liveHint && Date.now() < liveHint.expiresMs && liveHint.accepts(client, liveHint.payload)) {
        ws.send(envelope('hint.created', liveHint.payload));
      }
    });
  });

  return {
    listen(port) {
      return new Promise((resolve) => server.listen(port, () => resolve(server.address().port)));
    },
    // Drop every open socket but keep serving, to exercise reconnection.
    dropConnections() {
      for (const client of clients) client.socket.terminate();
    },
    close() {
      if (expiryTimer !== null) clearTimeout(expiryTimer);
      for (const client of clients) client.socket.terminate();
      sockets.close();
      return new Promise((resolve) => server.close(resolve));
    },
  };
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const port = await createMockBackend().listen(Number(process.env.PORT) || 8787);
  console.log(`Mock Mochi gateway (stand-in: two words and one hesitation) on http://localhost:${port}`);
  console.log(`  start:  curl -X POST localhost:${port}/api/sessions/demo/start`);
  console.log(`  say:    curl -X POST localhost:${port}/dev/sessions/demo/turn -H 'content-type: application/json' -d '{"text":"I wanted to go, but..."}'`);
}
