// =============================================================================
// PhoneApp.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// A PERSON'S PHONE (company version).  /m?user=ana  and  /m/analytics?user=ana
// Two tabs, switched with the bar at the bottom WITHOUT reloading the page:
//   Session   (SessionView.tsx):   Start session → Mochi joins the meeting live through this phone
//   Analytics (AnalyticsView.tsx): words to learn and how the sessions went
// The microphone lives HERE, above both tabs, so looking at Analytics during a session does not
// drop the phone out of the call (a page reload would).
// =============================================================================

import { type RefObject, useEffect, useState } from "react";
import type { Language } from "../contracts.ts";
import type { Backend } from "../lib/backend.ts";
import { copyFor } from "../lib/i18n.ts";
import type { ClientState } from "../lib/store.ts";
import { type Tab, tabFromPath, tabHref } from "../lib/tabs.ts";
import { usePhoneMic } from "../lib/usePhoneMic.ts";
import { AnalyticsView } from "./AnalyticsView.tsx";
import { SessionView } from "./SessionView.tsx";
import { TabBar } from "./TabBar.tsx";

interface Props {
  user: string;                        // "ana" or "ben" (the backend roster)
  state: ClientState;                  // everything received from the backend
  now: number;                         // current time (hints disappear on time)
  lang: Language;
  connected: boolean;                  // is the connection to the backend open?
  backend: RefObject<Backend | null>;  // Start / Stop
}

export function PhoneApp({ user, state, now, lang, connected, backend }: Props) {
  const t = copyFor(lang);
  const [tab, setTab] = useState<Tab>(() => tabFromPath(window.location.pathname));
  const [micError, setMicError] = useState<string | null>(null);
  const capturing = state.session?.capturing ?? false;
  const mic = usePhoneMic(capturing, (problem) => setMicError(t.micProblem[problem]));

  // Switch tabs: change the address (so a reload or a shared link opens the same tab) without reloading.
  const go = (next: Tab) => {
    if (next === tab) return;
    window.history.pushState(null, "", tabHref(next, window.location.search));
    setTab(next);
    window.scrollTo(0, 0);
  };

  // The phone's Back button moves between the tabs too.
  useEffect(() => {
    const onPop = () => setTab(tabFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  return (
    <>
      {tab === "session" ? (
        <SessionView user={user} state={state} now={now} lang={lang} connected={connected} backend={backend}
          mic={mic} micError={micError} clearMicError={() => setMicError(null)} />
      ) : (
        <AnalyticsView user={user} state={state} lang={lang} connected={connected}
          live={capturing && mic.here} onBackToSession={() => go("session")} />
      )}
      <TabBar current={tab} onSelect={go} lang={lang} />
    </>
  );
}
