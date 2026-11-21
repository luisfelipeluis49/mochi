// Demo mode: replays example Fluency Helper suggestions in a loop, with no
// backend. Same start()/stop() shape as lib/connection.js, and it produces the
// same text frames a real gateway would send.
//
// The MVP is English and Brazilian Portuguese, so the loop shows both
// directions and both shapes the glasses handle:
//   1. speaking English, stuck after "but": three candidates, meanings in Portuguese
//   2. speaking Portuguese, stuck after "mas": three candidates, meanings in English
//   3. a single word (the example in the team contract)

import { STATUS } from './connection.js';

const HINT_MS = 8000;

// Offsets in ms from the start of one loop. Every hint is aimed at nobody (target_user_id null),
// which the contract shows to everyone: the glasses only show hints for their wearer, and the
// demo has to work whoever that is.
export const SCRIPT = [
  {
    at: 0,
    type: 'session.state.changed',
    payload: {
      status: 'active', mode: 'together', focus: 'en', capturing: true,
      participants: ['ana', 'ben'],
    },
  },
  {
    at: 3000,
    type: 'hint.created',
    payload: {
      hint_id: 'hint_101', target_user_id: null, target_language: 'en',
      expression: 'although', meaning: 'embora', example: null, reason: 'trails_off',
      context: 'I wanted to go, but',
      candidates: [
        { expression: 'although', meaning: 'embora' },
        { expression: 'unfortunately', meaning: 'infelizmente' },
        { expression: 'instead', meaning: 'em vez disso' },
      ],
    },
  },
  {
    at: 16000,
    type: 'hint.created',
    payload: {
      hint_id: 'hint_102', target_user_id: null, target_language: 'pt-BR',
      expression: 'infelizmente', meaning: 'unfortunately', example: null, reason: 'trails_off',
      context: 'Eu queria ir, mas',
      candidates: [
        { expression: 'infelizmente', meaning: 'unfortunately' },
        { expression: 'acabei ficando', meaning: 'I ended up staying' },
        { expression: 'não deu tempo', meaning: 'there was no time' },
      ],
    },
  },
  {
    at: 29000,
    type: 'hint.created',
    payload: {
      hint_id: 'hint_103', target_user_id: null, target_language: 'en',
      expression: 'postpone', meaning: 'adiar',
      example: 'I need to postpone my meeting.', reason: 'code_switch',
    },
  },
];
const LOOP_MS = 42000;

export function createMockSource({ onMessage, onStatus }) {
  let timers = [];
  let sequence = 0;
  let running = false;

  function emit(step) {
    if (!running) return;
    const now = Date.now();
    sequence += 1;
    const payload = { ...step.payload };
    if (step.type === 'hint.created') {
      payload.expires_at = new Date(now + HINT_MS).toISOString();
    }
    onMessage(JSON.stringify({
      schema_version: '0.4',
      event_id: `evt_mock_${sequence}`,
      type: step.type,
      session_id: 'demo',
      emitted_at: new Date(now).toISOString(),
      sequence,
      payload,
    }));
  }

  function playLoop() {
    if (!running) return;
    timers = SCRIPT.map((step) => setTimeout(() => emit(step), step.at));
    timers.push(setTimeout(playLoop, LOOP_MS));
  }

  return {
    start() {
      if (running) return;
      running = true;
      onStatus(STATUS.ONLINE);
      playLoop();
    },
    stop() {
      running = false;
      timers.forEach(clearTimeout);
      timers = [];
    },
  };
}
