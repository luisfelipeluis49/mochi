// =============================================================================
// DebugPanel.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// The small black box you see when you add ?debug=1 to any page.
// It lists the LAST TEN events received from the backend (newest on top).
// Use it when something doesn't appear on screen: if the event is in this list,
// the problem is in our page; if it is NOT in the list, the backend never sent it.
// =============================================================================

import type { MochiEvent } from "../contracts.ts";

export function DebugPanel({ log, connected }: { log: MochiEvent[]; connected: boolean }) {
  return (
    <aside className="debug" aria-label="Debug: last ten events">
      {/* Header: is the connection open, and how many events are listed */}
      <div className="debug-head">debug · socket {connected ? "open" : "closed"} · last {log.length} events</div>
      <ol>
        {log.map((e, i) => (
          // One line per event: #sequence number, type, time, then the full payload as text
          <li key={`${i}-${e.event_id}`}>
            <b>#{e.sequence}</b> {e.type} <span>{e.emitted_at.slice(11, 19)}</span>
            <pre>{JSON.stringify(e.payload)}</pre>
          </li>
        ))}
      </ol>
    </aside>
  );
}
