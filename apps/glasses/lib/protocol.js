// Mochi event handling for the glasses (Mochi AR, Fluency Helper). Pure
// functions: no sockets, no timers, no UI.
//
// Event shapes come from the team contract (draft v0.4, section 6). The
// product vision (Nov 20) asks for one to three suggestions and an optional
// line of context, which the contract's Hint does not have yet. This file
// reads two PROPOSED optional fields on `hint.created`:
//
//   "candidates": [ { "expression": "although", "meaning": "embora" }, ... ]
//   "context":    "I wanted to go, but"
//
// A v0.4 hint without them still works: its `expression` and `meaning` are
// shown as the only suggestion.
//
// The glasses never decide who sees a suggestion or when. The backend does;
// whatever arrives on this person's connection is shown.

export const EVENT = {
  SESSION_STATE_CHANGED: 'session.state.changed',
  HINT_CREATED: 'hint.created',
  HINT_CLEARED: 'hint.cleared',
};

// Contract default: a hint stays for 8 seconds.
export const DEFAULT_HINT_MS = 8000;
// Safety cap so a malformed expires_at cannot pin text in someone's view.
export const MAX_HINT_MS = 60000;
// "One to three short candidate words or phrases." Extra ones are dropped.
export const MAX_CANDIDATES = 3;
// The context line is a reminder of where the speaker stopped, not a transcript.
export const MAX_CONTEXT_CHARS = 40;

export function initialState() {
  return {
    lastSequence: null, // highest envelope sequence applied on this connection
    capturing: false, // true between Start and Stop
    // { hintId, context, candidates: [{ expression, meaning }], hideAtMs } or null
    hint: null,
  };
}

// A new connection starts from the snapshot the server sends on connect, so
// sequence tracking restarts with it (the server may have restarted too).
export function resetForNewConnection(state) {
  return { ...state, lastSequence: null };
}

// Text frame -> event envelope, or null when it is not one.
export function parseEvent(raw) {
  if (typeof raw !== 'string') return null;
  let event;
  try {
    event = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!event || typeof event !== 'object' || Array.isArray(event)) return null;
  if (typeof event.type !== 'string') return null;
  if (!Number.isFinite(event.sequence)) return null;
  if (!event.payload || typeof event.payload !== 'object') return null;
  return event;
}

function toMs(isoString) {
  if (typeof isoString !== 'string') return NaN;
  return Date.parse(isoString);
}

// How long from now (device time) the hint should stay.
//
// The contract says a screen removes a hint at `expires_at`. That is a time on
// the server's clock. When the device clock gives a plausible answer we use
// it, which is also right for a hint replayed on reconnect. When it does not
// (the hint looks already over, or looks longer than its own total life), the
// device clock is off, and we fall back to the length the server gave it.
export function hintLifetimeMs(event, nowMs) {
  const expiresMs = toMs(event.payload.expires_at);
  if (!Number.isFinite(expiresMs)) return DEFAULT_HINT_MS;

  const emittedMs = toMs(event.emitted_at);
  const totalMs = Number.isFinite(emittedMs) ? expiresMs - emittedMs : NaN;
  const remainingMs = expiresMs - nowMs;

  if (Number.isFinite(totalMs) && totalMs > 0) {
    const plausible = remainingMs > 0 && remainingMs <= totalMs;
    return Math.min(plausible ? remainingMs : totalMs, MAX_HINT_MS);
  }
  if (remainingMs > 0) return Math.min(remainingMs, MAX_HINT_MS);
  return DEFAULT_HINT_MS;
}

function text(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function toCandidate(entry) {
  if (!entry || typeof entry !== 'object') return null;
  const expression = text(entry.expression);
  if (!expression) return null;
  return { expression, meaning: text(entry.meaning) };
}

// The suggestions in a Hint payload: the proposed `candidates` list when it
// has any usable entry, otherwise the v0.4 single expression. No duplicates,
// at most three.
export function candidatesOf(payload) {
  const listed = Array.isArray(payload.candidates) ? payload.candidates : [];
  const source = listed.some((entry) => toCandidate(entry)) ? listed : [payload];
  const seen = new Set();
  const candidates = [];
  for (const entry of source) {
    const candidate = toCandidate(entry);
    if (!candidate) continue;
    const key = candidate.expression.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    candidates.push(candidate);
    if (candidates.length === MAX_CANDIDATES) break;
  }
  return candidates;
}

// Where the speaker stopped, kept short: the end of the sentence matters, so a
// long context loses its beginning, cut at a word where possible.
export function contextLine(value) {
  const full = text(value).replace(/\s+/g, ' ').replace(/[.…\s]+$/, '');
  if (!full) return '';
  if (full.length <= MAX_CONTEXT_CHARS) return `${full}…`;
  const tail = full.slice(full.length - MAX_CONTEXT_CHARS);
  const firstSpace = tail.indexOf(' ');
  const fromWord = firstSpace >= 0 && firstSpace < tail.length - 1 ? tail.slice(firstSpace + 1) : tail;
  return `…${fromWord}…`;
}

// Apply one event. Returns the same state object when nothing changed.
export function reduce(state, event, nowMs) {
  if (state.lastSequence !== null && event.sequence <= state.lastSequence) {
    return state; // already applied
  }
  const next = { ...state, lastSequence: event.sequence };
  const payload = event.payload;

  switch (event.type) {
    case EVENT.SESSION_STATE_CHANGED:
      next.capturing = payload.capturing === true;
      return next;

    case EVENT.HINT_CREATED: {
      const candidates = candidatesOf(payload);
      if (text(payload.hint_id) === '' || candidates.length === 0) return next;
      next.hint = {
        hintId: payload.hint_id,
        context: contextLine(payload.context),
        candidates,
        hideAtMs: nowMs + hintLifetimeMs(event, nowMs),
      };
      return next;
    }

    case EVENT.HINT_CLEARED:
      if (state.hint && state.hint.hintId === payload.hint_id) next.hint = null;
      return next;

    default:
      // Game, learning and speak events are for other surfaces.
      return next;
  }
}

// Remove a hint whose time is up. Returns the same state when nothing changed.
export function expire(state, nowMs) {
  if (state.hint && nowMs >= state.hint.hideAtMs) return { ...state, hint: null };
  return state;
}

// The wearer dismissed the suggestions themselves. Local only; nothing is sent.
export function dismiss(state) {
  return state.hint ? { ...state, hint: null } : state;
}

// 'https://host' or 'wss://host' -> 'wss://host/ws?user=ana&surface=ar'
//
// `user` is the contract's Mobile-view connection. `surface=ar` is a PROPOSED
// addition so the gateway can send Fluency Helper suggestions to glasses only
// (the vision makes them AR-exclusive). A gateway that does not know the
// parameter ignores it and treats the glasses as that person's Mobile view.
export function socketUrl(backendUrl, userId) {
  const base = String(backendUrl || '').trim().replace(/\/+$/, '');
  if (!base) return '';
  const wsBase = base.replace(/^http(s?):\/\//i, 'ws$1://');
  return `${wsBase}/ws?user=${encodeURIComponent(userId)}&surface=ar`;
}
