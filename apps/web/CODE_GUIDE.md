# apps/web: every file, grouped by language

Every file below has comments at the top saying what it does, and notes beside the code.
The files stay in their folders (`src/lib`, `src/views`, ...) because Vite and React expect this layout. This guide groups them by language instead.

## How the pieces connect

```text
index.html  ──loads──▶  main.tsx  ──"which page?"──▶  who.ts
                           │
                           ▼
                       useMochi.ts ──connects──▶ backend.ts ──▶ Luís's backend (or the mock: demoScript.ts)
                           │                         │
                           │       every event ──▶ store.ts (remembers it)
                           ▼
              HomeView / PhoneApp (SessionView + AnalyticsView) / AudienceView  (draw it; texts from i18n.ts, colors from styles.css)
                  │                 ├── SessionView asks sessionStage.ts (= home.ts) what to show live
                  │                 └── AnalyticsView asks analytics.ts for the progress numbers
                  │
                  └── HomeView asks home.ts "which screen, and what does a tap do?"
```

## 1. TypeScript + JSX (`.tsx`): the screens (React components)

JSX is the HTML-looking code inside TypeScript, like `<p className="big">{word}</p>`.

| File | What it does |
|---|---|
| `src/main.tsx` | Starting point. Reads the URL, picks the screen, draws it |
| `src/views/StartPage.tsx` | The page at `/`: goes straight to this phone's owner's page; first time, explains how to open your link |
| `src/views/HomeView.tsx` | Mochi's 3.5-inch screen: face, the mode question, hints, what Mochi says, the game. Turns touches into tap / long press |
| `src/views/PhoneApp.tsx` | A person's phone: the two tabs (Session, Analytics), switched without reloading; keeps the phone's mic on across tabs |
| `src/views/SessionView.tsx` | The Session tab: Start session / Stop session, and the live stage that behaves like Mochi's screen (face, hint, what Mochi says, who is talking) |
| `src/views/AnalyticsView.tsx` | The Analytics tab: progress numbers, last session, sessions bars, "Words to learn" cards |
| `src/views/TabBar.tsx` | The Session / Analytics buttons at the bottom of the phone |
| `src/views/AudienceView.tsx` | The projector. Never shows the secret word during a round |
| `src/views/DebugPanel.tsx` | The `?debug=1` list of the last 10 events |

## 2. TypeScript (`.ts`): the logic, with no screen

| File | What it does |
|---|---|
| `src/lib/store.ts` | The page's memory: applies each event from the backend |
| `src/lib/analytics.ts` | Counts the numbers for the phone: words by step, minutes, sessions in order, bar sizes |
| `src/lib/sessionStage.ts` | What the Session tab shows live: the same choice as Mochi's screen (home.ts), without the game |
| `src/lib/tabs.ts` | The two phone tabs and their addresses (`/m`, `/m/analytics`) |
| `src/lib/usePhoneMic.ts` / `phoneMic.ts` / `phoneSession.ts` | The phone as Mochi's microphone: ask for the mic, join the phone's own Agora session, leave on Stop |
| `src/lib/home.ts` | The rules of Mochi's screen and the game (which screen, what a tap does) |
| `src/lib/backend.ts` | The **only** file that talks to the backend (WebSocket + POST requests) |
| `src/lib/useMochi.ts` | React hook: connects once, keeps the data, ticks the clock |
| `src/lib/people.ts` | Each phone remembers its owner; reading `?people=` for the demo |
| `src/lib/who.ts` | URL → "am I Mochi, a phone, or the projector?" |
| `src/lib/i18n.ts` | Every text on screen, in English and Portuguese |
| `src/contracts.ts` | The shape of every message (types only). Temporary until Matheus's `packages/contracts` exists. Lines marked `PROPOSED v0.5` are the proposal |
| `src/mock/demoScript.ts` | A fake backend that replays the new demo with Ana and Sophie (`?mock=1`) |
| `vite.config.ts` | Settings for Vite: the dev server and forwarding `/api` and `/ws` to the backend |

**Tests** (also TypeScript, run with `npm test`):

| File | Checks |
|---|---|
| `src/lib/store.test.ts` | duplicates ignored, hints expire, word order, debug list |
| `src/lib/analytics.test.ts` | the progress numbers, session order, bar sizes |
| `src/lib/sessionStage.test.ts` | the Session tab: idle, listening, hint with meaning and example, Mochi speaking, no game on the phone |
| `src/lib/tabs.test.ts` | the tab of each address; switching keeps the person and options |
| `src/lib/contract.test.ts` | the app against the OFFICIAL contract in `packages/contracts`: every example event, every field the screens read, the learning states |
| `src/lib/home.test.ts` | the mode question, hint options, Mochi speaking, every game step, text size |
| `src/mock/demoScript.test.ts` | the secret word only reaches Mochi's screen; words and summaries only reach their owner; the story runs in order |

## 3. CSS

| File | What it does |
|---|---|
| `src/styles.css` | All colors, sizes and layout, with one section per screen. Colors are variables at the top, from the product vision slides |

## 4. HTML

| File | What it does |
|---|---|
| `index.html` | The one HTML page. Nearly empty: React draws everything inside `<div id="root">` |

## 5. JSON (settings)

| File | What it does |
|---|---|
| `package.json` | The project's name, its libraries (`react`, `vite`, ...) and its commands: `npm run dev`, `npm test`, `npm run build`. JSON can't hold comments, so here is what it does. |
| `tsconfig.json` | How strict TypeScript is. This one allows comments. |
| `vercel.json` | Settings to host the app on Vercel (build command, output folder, every address opens the app) |

## 6. Markdown (documentation)

| File | What it does |
|---|---|
| `README.md` | How to run the app, plus the report and open questions for the team |
| `CODE_GUIDE.md` | This file |
| `PROPOSAL_contracts_v0.5.md` | What the new vision needs from the contracts, for the team to approve |

## Where to change common things

- **A sentence on any screen:** `src/lib/i18n.ts`. Change it in both languages.
- **A color or size:** `src/styles.css` (the colors are variables at the top: `--night`, `--cream`, `--pink`...).
- **The backend address:** `vite.config.ts` (during development) or `VITE_BACKEND_URL`.
- **How the game reacts to taps:** `src/lib/home.ts`, then run `npm test`.
- **When we get the real contracts:** replace `src/contracts.ts` with Matheus's types.
