// One WebSocket to the Mochi gateway that keeps itself alive.
//
// Glasses change network often (phone tether, Wi-Fi), and the runtime may
// close a socket when the route changes. So: reconnect, with a short growing
// wait, until stop() is called. On every new connection the server sends the
// current session state and any live hint, so nothing is replayed locally.

const RETRY_MS = [1000, 2000, 5000];

export const STATUS = {
  CONNECTING: 'connecting',
  ONLINE: 'online',
  RECONNECTING: 'reconnecting',
};

export function createConnection({ url, onMessage, onStatus, WebSocketImpl }) {
  const Socket = WebSocketImpl || globalThis.WebSocket;
  let socket = null;
  let retryTimer = null;
  let attempts = 0;
  let running = false;

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

    current.onopen = () => {
      if (socket !== current) return;
      attempts = 0;
      onStatus(STATUS.ONLINE);
    };
    current.onmessage = (event) => {
      if (socket !== current) return;
      onMessage(event.data);
    };
    current.onerror = () => {
      // A close event always follows; the retry is scheduled there.
    };
    current.onclose = () => {
      if (socket !== current) return;
      socket = null;
      if (running) scheduleRetry();
    };
  }

  function scheduleRetry() {
    if (!running || retryTimer !== null) return;
    onStatus(STATUS.RECONNECTING);
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
