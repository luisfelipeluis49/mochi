// =============================================================================
// useMochi.ts  —  LANGUAGE: TypeScript (a React "hook")
// -----------------------------------------------------------------------------
// The bridge between the backend and React. A "hook" is a function React
// components call to get data that changes over time. This one:
//   1. opens the connection once (real backend, or the mock with ?mock=1)
//   2. runs every incoming event through applyEvent() (store.ts)
//   3. ticks a clock 4 times per second, so hints disappear exactly on time
// Every screen gets its data from here (see main.tsx).
// =============================================================================

import { useEffect, useRef, useState } from "react";
import { type Backend, connectMock, connectReal } from "./backend.ts";
import { type ClientState, applyEvent, initialState, onNewConnection } from "./store.ts";
import type { Who } from "./who.ts";

export function useMochi(who: Who, opts: { mock: boolean; mockSpeed: number }) {
  const [state, setState] = useState<ClientState>(initialState); // everything received so far
  const [connected, setConnected] = useState(false);              // is the connection open?
  const [now, setNow] = useState(() => Date.now());               // the current time
  const [rejected, setRejected] = useState<string | null>(null);  // why the backend refused us (close 4400)
  const backend = useRef<Backend | null>(null);                   // the object used to send commands
  const key = JSON.stringify(who);                                // reconnect only if "who" really changes

  // Runs when the page opens: connect. The function returned at the end runs when the page closes: disconnect.
  useEffect(() => {
    const handlers = {
      // Each event updates the state through applyEvent (store.ts).
      onEvent: (e: Parameters<typeof applyEvent>[1]) => setState((s) => applyEvent(s, e, Date.now())),
      onRejected: (reason: string) => setRejected(reason),
      onConnected: (c: boolean) => {
        setConnected(c);
        if (c) { setRejected(null); setState(onNewConnection); } // new connection: forget old sequence numbers
      },
    };
    const b = opts.mock ? connectMock(who, handlers, opts.mockSpeed) : connectReal(who, handlers);
    backend.current = b;
    return () => b.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, opts.mock, opts.mockSpeed]);

  // The clock: update "now" every 250 ms so expired hints and the result screen go away on time.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, []);

  return { state, connected, now, backend, rejected };
}
