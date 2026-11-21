// =============================================================================
// main.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// The STARTING POINT of the whole web app. The browser runs this file first.
// Its job:
//   1. read the address bar (URL) to know WHICH page this is (Mochi, phone, projector)
//   2. read the options in the URL (?mock=1, ?debug=1, ?lang=pt-BR ...)
//   3. draw the right screen inside <div id="root"> in index.html
// =============================================================================

// --- Imports: bring in code from React and from our other files ---------------
import { StrictMode } from "react";                    // React helper that warns about mistakes while developing
import { createRoot } from "react-dom/client";        // connects React to the real web page
import { pickLanguage } from "./lib/i18n.ts";        // decides English or Portuguese
import { useMochi } from "./lib/useMochi.ts";        // connects to the backend and keeps the data
import { type Who, whoFromUrl } from "./lib/who.ts"; // turns the URL into "which page am I?"
import { AudienceView } from "./views/AudienceView.tsx"; // projector screen
import { DebugPanel } from "./views/DebugPanel.tsx";     // the ?debug=1 event list
import { HomeView } from "./views/HomeView.tsx";
import { InsightsView } from "./views/InsightsView.tsx";         // Mochi's own little screen
import { MobileView } from "./views/MobileView.tsx";
import { StartPage } from "./views/StartPage.tsx";
import { TabBar } from "./views/TabBar.tsx";                  // the Analytics / Conversations bar on phone pages
import { peopleFromUrl, rememberUser } from "./lib/people.ts";     // a person's phone screen
import "./styles.css";                                  // all the colors and sizes (CSS)

// --- Read the options from the URL --------------------------------------------
// Example URL: http://localhost:5173/m?user=ana&mock=1&lang=pt-BR
const q = new URLSearchParams(window.location.search);          // the part after "?"
const lang = pickLanguage(window.location.search, navigator.language); // "en" or "pt-BR"
const debug = q.get("debug") === "1";                            // show the event list?
const mock = q.get("mock") === "1";                              // use fake data instead of the backend?
const mockSpeed = Number(q.get("speed") ?? "1") || 1;            // make the fake demo run faster (e.g. 4 = 4x)
const insights = window.location.pathname.startsWith("/me");      // the "My conversations" page
const mockPeople = peopleFromUrl(window.location.search) ?? undefined; // ?people=tasnim,matheus: names in the mock demo

// --- App: the page shown when the URL is one of our 3 screens -----------------
// "who" says which connection this is: the Mochi device, a user (ana/ben, or anyone in the backend roster), or the projector.
function App({ who }: { who: Who }) {
  // useMochi opens the connection and gives back:
  //   state     = everything received so far (session, hint, game, words)
  //   connected = is the connection open right now?
  //   now       = the current time, updated 4x per second (so hints disappear on time)
  //   backend   = an object with functions to send commands (start, stop, game result)
  const { state, connected, now, backend, rejected } = useMochi(who, { mock, mockSpeed, mockPeople, mockScenario: insights ? "recording" : "demo" });

  // Draw ONE of the three screens depending on "who".
  // `condition && <Thing />` means "draw Thing only if condition is true".
  return (
    <>
      {who.kind === "device" && <HomeView state={state} now={now} lang={lang} backend={backend} />}
      {/* /me?user=... → "My conversations" (the person's analytics); /m?user=... → the phone page */}
      {who.kind === "user" && insights && <InsightsView user={who.user} state={state} now={now} lang={lang} connected={connected} backend={backend} />}
      {who.kind === "user" && !insights && (
        <MobileView user={who.user} state={state} now={now} lang={lang} connected={connected} backend={backend} />
      )}
      {/* Phone pages: the Analytics / Conversations bar at the bottom */}
      {who.kind === "user" && <TabBar current={insights ? "conversations" : "analytics"} search={window.location.search} lang={lang} />}
      {who.kind === "audience" && <AudienceView state={state} now={now} lang={lang} />}
      {rejected && <p className="fatal" role="alert">Connection refused by the backend: {rejected}</p>}
      {debug && <DebugPanel log={state.log} connected={connected} />}
    </>
  );
}

// --- "/" shows the StartPage (views/StartPage.tsx): choose who you are, or open a screen.

// --- Decide which page this is, then draw it -----------------------------------
const who = whoFromUrl(window.location.pathname, window.location.search); // null if the URL is not one of our pages
// A personal page (/me?user=tasnim or /m?user=tasnim) tells this phone whose it is; "/" opens it next time.
if (who?.kind === "user") rememberUser(who.user);
document.body.dataset.view = who?.kind ?? "index";   // adds data-view="device"/"user"/... to <body> so CSS can style each page
if (q.get("projector") === "1") document.body.classList.add("projector"); // bigger layout for the projector

// Put the React app inside <div id="root"></div> from index.html.
createRoot(document.getElementById("root")!).render(
  <StrictMode>{who ? <App who={who} /> : <StartPage lang={lang} />}</StrictMode>,
);
