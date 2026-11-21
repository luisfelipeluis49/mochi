// One WebSocket to the Mochi gateway that keeps itself alive.
//
// Glasses change network often (phone tether, Wi-Fi), and the runtime may
// close a socket when the route changes. So: reconnect, with a short growing
// wait, until stop() is called. On every new connection the server sends the
// current session state and any live hint, so nothing is replayed locally.
//
// Three things the real backend taught us:
// - It accepts a bad `?user=` and then closes with code 4400. So "open" proves
//   nothing: the backoff resets, and the status becomes ONLINE, only on the
//   first valid event received on that socket.
// - Close code 4400 is final: stop retrying and show the reason (REJECTED).
// - A sleeping host can take a long time to answer. A socket that has not
//   opened after `connectTimeoutMs` is closed and retried, shown as WAKING_UP.

import { parseEvent } from './protocol.js';

const OPEN_STATE = 1; // WebSocket.OPEN
const RETRY_MS = [1000, 2000, 5000];
const CONNECT_TIMEOUT_MS = 8000;
export const CLOSE_REJECTED = 4400;

export const STATUS = {
  CONNECTING: 'connecting',
  ONLINE: 'online',
  RECONNECTING: 'reconnecting',
  WAKING_UP: 'waking-up',
  REJECTED: 'rejected',
};

export function createConnection({ url, onMessage, onStatus, WebSocketImpl, connectTimeoutMs = CONNECT_TIMEOUT_MS }) {
  const Socket = WebSocketImpl || globalThis.WebSocket;
  let socket = null;
  let retryTimer = null;
  let connectTimer = null;
  let attempts = 0;
  let running = false;

  function clearConnectTimer() {
    if (connectTimer !== null) {
      clearTimeout(connectTimer);
      connectTimer = null;
    }
  }

  function open() {
    retryTimer = null;
    if (!running) return;
    let current;
    try {
      current = new Socket(url);
    } catch (error) {
      console.error('[mochi] cannot open socket:', error && error.message);
      scheduleRetry();
      return;
    }
    socket = current;
    let validated = false;

    clearConnectTimer();
    connectTimer = setTimeout(() => {
      connectTimer = null;
      if (socket !== current) return;
      socket = null;
      try {
        current.close();
      } catch {
        // already closed
      }
      scheduleRetry(STATUS.WAKING_UP);
    }, connectTimeoutMs);

    current.onopen = () => {
      if (socket !== current) return;
      clearConnectTimer();
      // Not ONLINE yet and no backoff reset: wait for a valid event.
    };
    current.onmessage = (event) => {
      if (socket !== current) return;
      if (!validated && parseEvent(event.data)) {
        validated = true;
        attempts = 0;
        onStatus(STATUS.ONLINE);
      }
      onMessage(event.data);
    };
    current.onerror = () => {
      // Some runtimes (Node 22's WebSocket) send `error` and never `close` when the connection cannot be
      // made, so a socket that is not open is given up here instead of waiting for a close that may not come.
      if (socket !== current || current.readyState === OPEN_STATE) return;
      socket = null;
      clearConnectTimer();
      try {
        current.close();
      } catch {
        // already closed
      }
      scheduleRetry();
    };
    current.onclose = (event) => {
      if (socket !== current) return;
      socket = null;
      clearConnectTimer();
      if (!running) return;
      if (event && event.code === CLOSE_REJECTED) {
        running = false;
        onStatus(STATUS.REJECTED, (event.reason || '').trim());
        return;
      }
      scheduleRetry();
    };
  }

  function scheduleRetry(status = STATUS.RECONNECTING) {
    if (!running || retryTimer !== null) return;
    onStatus(status);
    const wait = RETRY_MS[Math.min(attempts, RETRY_MS.length - 1)];
    attempts += 1;
    retryTimer = setTimeout(open, wait);
  }

  return {
    start() {
      if (running) return;
      running = true;
      attempts = 0;
      onStatus(STATUS.CONNECTING);
      open();
    },
    stop() {
      running = false;
      if (retryTimer !== null) {
        clearTimeout(retryTimer);
        retryTimer = null;
      }
      clearConnectTimer();
      const current = socket;
      socket = null;
      if (current) {
        try {
          current.close();
        } catch {
          // already closed
        }
      }
    },
  };
}
