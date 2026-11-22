// The small part of the Web Storage API the app uses, and safe access to it.
// Every call is wrapped: a private window or blocked site data can make storage throw.

export type KV = Pick<Storage, "getItem" | "setItem" | "removeItem">;

export function localStore(): KV | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function sessionStore(): KV | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export function safeGet(s: KV | null, key: string): string | null {
  try {
    return s?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function safeSet(s: KV | null, key: string, value: string): boolean {
  try {
    if (!s) return false;
    s.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function safeRemove(s: KV | null, key: string): void {
  try {
    s?.removeItem(key);
  } catch {
    /* nothing to do */
  }
}

/** A Map-backed KV, for tests and as an in-memory fallback. */
export function memoryStore(): KV & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, String(v)),
    removeItem: (k) => void data.delete(k),
  };
}

/** A KV whose every call throws, for tests. */
export function throwingStore(): KV {
  const boom = () => {
    throw new Error("storage blocked");
  };
  return { getItem: boom, setItem: boom, removeItem: boom };
}
