// Helpers shared by the tests (not used by the app at run time).

export interface FakeCall {
  url: string;
  method: string;
  body: unknown;
  headers: Record<string, string>;
  signal: AbortSignal | null | undefined;
}

/** A fake fetch that records calls and answers with the handler's (status, json). */
export function fakeFetch(handler: (c: FakeCall) => { status: number; json?: unknown } | "throw" | "hang") {
  const calls: FakeCall[] = [];
  const fn = (url: string, init?: RequestInit): Promise<Response> => {
    const c: FakeCall = {
      url,
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : init?.body ?? undefined,
      headers: (init?.headers as Record<string, string>) ?? {},
      signal: init?.signal,
    };
    calls.push(c);
    const r = handler(c);
    if (r === "throw") return Promise.reject(new TypeError("Failed to fetch"));
    if (r === "hang") {
      return new Promise((_, reject) => {
        c.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    }
    return Promise.resolve(new Response(r.json === undefined ? null : JSON.stringify(r.json), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    }));
  };
  return { fn, calls };
}

/** Manual timers: run them with tick(ms). */
export function fakeTimers() {
  let now = 0;
  let next = 1;
  const queue = new Map<number, { at: number; fn: () => void }>();
  return {
    now: () => now,
    setTimeout: (fn: () => void, ms: number): unknown => {
      const id = next++;
      queue.set(id, { at: now + ms, fn });
      return id;
    },
    clearTimeout: (id: unknown) => void queue.delete(id as number),
    pending: () => queue.size,
    tick(ms: number) {
      const end = now + ms;
      for (;;) {
        let best: [number, { at: number; fn: () => void }] | null = null;
        for (const e of queue) if (e[1].at <= end && (!best || e[1].at < best[1].at)) best = e;
        if (!best) break;
        queue.delete(best[0]);
        now = best[1].at;
        best[1].fn();
      }
      now = end;
    },
  };
}

export const flush = () => new Promise<void>((r) => setImmediate(r));
