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
import { type Who, indexLinks, whoFromUrl } from "./lib/who.ts"; // turns the URL into "which page am I?"
import { AudienceView } from "./views/AudienceView.tsx"; // projector screen
import { DebugPanel } from "./views/DebugPanel.tsx";     // the ?debug=1 event list
import { HomeView } from "./views/HomeView.tsx";         // Mochi's own little screen
import { MobileView } from "./views/MobileView.tsx";     // a person's phone screen
import "./styles.css";                                  // all the colors and sizes (CSS)

// --- Read the options from the URL --------------------------------------------
// Example URL: http://localhost:5173/m?user=ana&mock=1&lang=pt-BR
const q = new URLSearchParams(window.location.search);          // the part after "?"
const lang = pickLanguage(window.location.search, navigator.language); // "en" or "pt-BR"
const debug = q.get("debug") === "1";                            // show the event list?
const mock = q.get("mock") === "1";                              // use fake data instead of the backend?
const mockSpeed = Number(q.get("speed") ?? "1") || 1;            // make the fake demo run faster (e.g. 4 = 4x)

// --- App: the page shown when the URL is one of our 3 screens -----------------
// "who" says which connection this is: the Mochi device, a user (ana/sophie), or the projector.
function App({ who }: { who: Who }) {
  // useMochi opens the connection and gives back:
  //   state     = everything received so far (session, hint, game, words)
  //   connected = is the connection open right now?
  //   now       = the current time, updated 4x per second (so hints disappear on time)
  //   backend   = an object with functions to send commands (start, stop, game result)
  const { state, connected, now, backend, rejected } = useMochi(who, { mock, mockSpeed });

  // Draw ONE of the three screens depending on "who".
  // `condition && <Thing />` means "draw Thing only if condition is true".
  return (
    <>
      {who.kind === "device" && <HomeView state={state} now={now} lang={lang} backend={backend} />}
      {who.kind === "user" && (
        <MobileView user={who.user} state={state} lang={lang} connected={connected} backend={backend} />
      )}
      {who.kind === "audience" && <AudienceView state={state} now={now} lang={lang} />}
      {rejected && <p className="fatal" role="alert">Connection refused by the backend: {rejected}</p>}
      {debug && <DebugPanel log={state.log} connected={connected} />}
    </>
  );
}

// --- Index: shown at "/" (no screen chosen). Just a list of links. -------------
function Index() {
  return (
    <main className="index">
      <h1>Mochi</h1>
      <ul>
        {indexLinks().map((l) => <li key={l.href}><a href={l.href}>{l.label}</a></li>)}
      </ul>
      <p>Add <code>?mock=1</code> to replay the demo without a backend, <code>&amp;debug=1</code> for the event list, <code>&amp;lang=pt-BR</code> for Portuguese, <code>&amp;projector=1</code> on a phone page to show it large on the projector.</p>
    </main>
  );
}

// --- Decide which page this is, then draw it -----------------------------------
const who = whoFromUrl(window.location.pathname, window.location.search); // null if the URL is not one of our pages
document.body.dataset.view = who?.kind ?? "index";   // adds data-view="device"/"user"/... to <body> so CSS can style each page
if (q.get("projector") === "1") document.body.classList.add("projector"); // bigger layout for the projector

// Put the React app inside <div id="root"></div> from index.html.
createRoot(document.getElementById("root")!).render(
  <StrictMode>{who ? <App who={who} /> : <Index />}</StrictMode>,
);
