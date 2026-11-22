# apps/web: engineering rules

Read the root `AGENTS.md` first. These rules add to it for the web app.

## Stack

- React 19, Vite 7, TypeScript (strict, `verbatimModuleSyntax`, `erasableSyntaxOnly`: no enums, no
  constructor parameter properties, no namespaces).
- **No new runtime dependencies.** No router, state library, chart library, icon set or CSS
  framework. The app has its own small History-API router (`lib/routes.ts`), one `useReducer` store
  (`lib/appState.ts` + `lib/events.ts`), inline SVG icons (`ui/Icons.tsx`) and plain CSS with custom
  properties.
- The Agora Web SDK is loaded from Agora's CDN at a pinned version (`lib/agora.ts`), only at Start.
- Tests use Node's test runner with `tsx`, which is the only dev dependency added. Components are
  tested with `react-dom/server` `renderToString`: no jsdom, no Testing Library, no browser.

## Where things go

- **Logic goes in pure modules in `src/lib/`, and each one has a `*.test.ts`.** A module there must
  not import React. It takes browser APIs (fetch, WebSocket, storage, timers, the clock) as
  parameters, so the tests can pass fakes.
- **Components stay thin** (`src/ui/`, `src/screens/`). They take props and do no fetching. Each has a
  `*.test.tsx`. Effects and wiring live in `src/hooks/`.
- **Tokens only.** Every color is defined once, in `src/styles/tokens.css`. `lib/tokens.test.ts`
  fails on a hex color anywhere else in `src/`. `lib/contrast.test.ts` checks every text and
  background pair against WCAG AA.
- **All copy goes in `src/lib/i18n.ts`**, in English and Brazilian Portuguese, with the same keys.
  This includes `aria-label`s and error messages. The backend's `detail` is never shown.
- Touch targets are at least 44 px (48 px for nav and primary buttons). `:focus-visible` is always
  visible. Nothing animates under `prefers-reduced-motion: reduce`.

## The contract

- The backend contract is THE SHARED CONTRACT: root `AGENTS.md` section 6.6 and `docs/DECISIONS.md`
  D-42. Event shapes are AGENTS.md section 6. `src/contracts.ts` mirrors them. Do not add, rename or
  remove a field there; propose the change to the owners.
- The app calls only its own origin: `/api/*`, `/ws`, `/healthz`. It never calls `/api/devices/*`,
  `/dev/*`, `/agora/*` or `/api/demo/reset`, and never uses the `demo` session.
- **Never decide visibility in the browser.** Show what the gateway sent to this connection, and
  nothing else. Never show a secret word.
- **Never store learning events.** The backend owns them. Nothing about training is kept in the browser.

## Before you finish

```bash
npm test && npx tsc --noEmit && npm run build
docker build -t mochi-web apps/web     # from the repo root, when you touched Dockerfile or nginx/
```
