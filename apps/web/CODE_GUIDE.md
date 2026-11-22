# apps/web code guide

How the pieces fit together. Product rules are in the root `AGENTS.md`; web rules are in `AGENTS.md`
here.

```text
main.tsx --builds--> AppDeps (real or ?mock=1)
   |
   v
hooks/useApp.ts --(useReducer: lib/appState.ts)--> AppModel + AppActions
   |    wires lib/api.ts, lib/socket.ts, lib/mic.ts, lib/probe.ts, hooks/useAgoraMic.ts
   v
App.tsx (no effects) --> screens/* --> ui/*
```

The startup order is the mic gate and the reachability probe, in parallel. Then comes the identity
(onboarding, or a check of the stored user), and then the app shell. A Start follows THE SHARED
CONTRACT C6 in `useApp.start`: open the socket on the new session id, `POST start`, `GET agora`, and
join with the microphone. When a step after the start fails, the app sends `POST stop`.

## Pure logic (`src/lib/`, each with a `*.test.ts`)

| File | What it does |
|---|---|
| `../contracts.ts` | The TypeScript types for the AGENTS 6 events and payloads, plus `User`, `SessionRecord` and `AgoraJoin` from the contract, and the type guards. The guards accept unknown extra keys. |
| `routes.ts` | Path to screen and screen to path. `/` and unknown paths go to `/session`. |
| `storage.ts` | Safe access to `localStorage`/`sessionStorage`: every call is wrapped. It also has fake stores for tests. |
| `identity.ts` | The user in `localStorage` `mochi.user.v1`: read, write, forget. Also the avatar initials. |
| `sessionId.ts` | `w-` plus 8 hex characters, and the `sessionStorage` slot `mochi.session.v1` used for a reload. |
| `api.ts` | The typed client for every endpoint the web uses (with an injectable `fetch`), `ApiError {status, kind}`, the 10 s `/healthz` timeout, and `beaconStop`. |
| `httpProblem.ts` | Maps a status code or network failure to a `ProblemKind` (section 6.1), including the 90 s waking-to-unreachable edge. |
| `probe.ts` | The `/healthz` probe loop: it retries after 2, 4 and 8 s, then every 15 s, and reports waking, unreachable or offline. |
| `socket.ts` | The `/ws?user=&session=` URL, the backoff (1, 2, 4, 8, then 15 s), message parsing, and the rule that close code 4400 means a lost user. |
| `events.ts` | The live-state reducer: drops duplicate `sequence` numbers, holds the session state, the live hint and its expiry (from the server's own times), the hints of this session, what Mochi said, and the words by id, and tracks the "used" and "proud" moments. |
| `appState.ts` | The app store: gate, probe, identity, socket, the session phase (idle, starting, capturing, stopping), banners, "ended elsewhere", reload/rejoin, volume, records, progress. |
| `mic.ts` | `runMicGate(env)` (secure context, `mediaDevices`, permissions query, `getUserMedia`, the 8 s "slow" prompt) and `micProblemOf(error)` (DOM names and Agora codes; the Agora codes are unverified). |
| `agora.ts` | Loads the SDK from the CDN (pinned 4.24.8) and wraps join, publish (AEC/ANS/AGC), play, volume, levels and leave behind `VoiceLink`. It reports failures as `VoiceError`: `agora_sdk`, `agora_join` or a mic problem. |
| `face.ts` | `faceOf(input, now)`: Mochi's mode, mood, word, note, who, badge and pop, as in the section 3.3 table. Also `speakingUntil`. |
| `training.ts` | `checkAnswer` (normalising, articles, accents, Levenshtein), the Leitner `schedule`, `dueCards`, `nextDue`, `ProgressStore` (`mochi.training.v1.<user>`), accuracy. |
| `digest.ts` | `buildDigest`: the wrap-up of one calendar week (Monday to Sunday, `weekKeys`) across all sessions: totals, the week before, minutes per day, words grouped by what happened that week, and what to practise next. |
| `analytics.ts` | `buildAnalytics`: tiles, the day streak, the bars for the last 10 records, the state counts, and `statePath`. |
| `i18n.ts` | All copy in `en` and `pt-BR` with the same keys (enforced by the types), `t`, `plural`, `languageName`, UI-language detection and storage, `wokenBy`. |
| `format.ts` | `Intl` dates (`en-GB` / `pt-BR`), minutes, `mm:ss`, relative times, `dayKey` (with an injectable time zone). |
| `contrast.ts` | The WCAG contrast ratio, and a reader for the hex tokens in a CSS file. |
| `testkit.ts` | Test helpers only: a fake `fetch`, fake timers, `flush`. |
| `tokens.test.ts` | Fails on any hex color outside `styles/tokens.css`. |

## Components (`src/ui/`, tested with `renderToString`)

| File | What it shows |
|---|---|
| `Face.tsx` | Mochi's presence panel: monogram, state text and an audio meter. CSS `mode-*` classes colour the meter; `has-problem` and `is-offline` mark errors. It has the volume pop and the offline label. `role="img"` with an `aria-label`. |
| `HintCard.tsx` | The live hint: the word (with `lang`), the note, the example, the countdown bar, "For everyone", and "★ You used it!". `aria-live`. |
| `SpeechBubble.tsx` | What Mochi said. `aria-live`. |
| `StatusChip.tsx` | Asleep, Waking up, Listening, or No connection. |
| `Nav.tsx` | One `<nav>` laid out as a tab bar, a rail or a side nav. `aria-current` on the active item. `Avatar`, `linkClick`. |
| `Problem.tsx` | A full-screen problem (`role="alert"`) for a `MicProblem` or a `ProblemKind`. |
| `Banner.tsx` | A non-blocking problem or notice. |
| `Icons.tsx` | The inline SVG icons. |

## Screens (`src/screens/`)

| File | Notes |
|---|---|
| `MicGate.tsx` | "Allow the microphone" while the browser asks, with "Allow microphone" after 8 s. Also `Loading`. |
| `Unreachable.tsx` | Shows waking, unreachable or offline while `/healthz` does not answer. |
| `Onboarding.tsx` | The name, plus the languages (pre-filled; they always differ). Shows the `profile_lost` note and the 422 and unreachable errors. |
| `SessionScreen.tsx` | The device (Mochi Home) in the browser. Two columns from 840 px. |
| `TrainingScreen.tsx` | `TrainingCard`, `TrainingDone`, `TrainingEmpty`, and the round logic. "Say it" appears only with `SpeechRecognition`. |
| `DigestScreen.tsx` / `AnalyticsScreen.tsx` | Render the view models from `lib/digest.ts` and `lib/analytics.ts`. The chart is SVG with a hidden table. |
| `ProfileScreen.tsx` | Languages, the UI language switch, and "Forget me on this device". |

`App.tsx` chooses between them in order (gate, probe, onboarding, shell) and has no effects, so
`App.test.tsx` renders it from `mock/model.ts`.

## Hooks (`src/hooks/`)

| File | What it does |
|---|---|
| `useApp.ts` | The wiring: the store, routing, `<html lang>`, the gate, the probe, the identity check, the words and records, the socket (it reconnects when the session id changes), `pagehide`, and Start, Stop, rejoin, onboarding, training and language. |
| `useAgoraMic.ts` | The voice link, and the microphone and voice levels sampled every 100 ms (hearing, speaking, the mouth). |
| `useNow.ts` | A clock tick (1 s, or 250 ms during a session). |

## Mock (`src/mock/`)

`backend.ts` is an in-page backend for `?mock=1`. It provides an `Api`, a `WebSocket` class, a fake
`VoiceLink`, the demo script and seeded history. `model.ts` builds a ready `AppModel` for the tests.

## Styles and infrastructure

| File | What it is |
|---|---|
| `styles/tokens.css` | The design tokens: the only colors in the app. The face colors map onto them. |
| `styles/app.css` | Layout (phone, tablet, desktop), components, the face, and reduced motion. |
| `index.html`, `public/favicon.svg` | The page, its theme color and the favicon. These are the only color values outside the tokens. |
| `vite.config.ts` | The React plugin and the dev proxy for `/api`, `/ws` and `/healthz`, set with `MOCHI_BACKEND_URL`. |
| `Dockerfile`, `.dockerignore` | Node 22 build, then `nginx:1.27-alpine`. |
| `nginx/default.conf.template` | The SPA, the proxy, caching and security headers. Only `${PORT}`, `${BACKEND_URL}` and `${BACKEND_HOST}` are substituted. |
| `nginx/15-backend-host.envsh` | Exports `BACKEND_HOST` (the host of `BACKEND_URL`) before envsubst runs. |
