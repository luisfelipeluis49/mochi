# Mochi web app (`apps/web`)

The web app does in a browser what Mochi Home (the Raspberry Pi) does, through the same backend. A
person tells Mochi their name and starts a session. Mochi listens through the browser's microphone,
shows a hint under its face when they get stuck on a word, and speaks through the Agora audio. The
app then keeps their words for Training, a Digest of each session, and Analytics.

It replaces the old app. The old `/home`, `/m` and `/audience` views are gone. Mochi's own screen is
now `hardware/pi-setup/face.html`. `PROPOSAL_contracts_v0.5.md` and `PROPOSAL_phone_microphone.md`
are kept as history only.

## Screens

| URL | Screen | What it does |
|---|---|---|
| `/welcome` | Onboarding | Asks for a name only, with the two languages pre-filled. `POST /api/users` creates the user id under which the data is stored. |
| `/session` | Session | Mochi Home in the browser: the face, the live hint, what Mochi said, Start and Stop, the hints of this session, and the voice volume. `/` goes here. |
| `/training` | Training | Spaced recall of the saved words. The prompt is the meaning, and the answer is typed or spoken. |
| `/digest` | Digest | A recap of the latest session (or a chosen one): new words, words used with help, words recalled in a game, today's totals, and what to practise next. |
| `/analytics` | Analytics | Tiles, minutes per session, where the words are, and each word's state path. |
| `/profile` | Profile | Name and languages, the interface language, and "Forget me on this device". |

The layout is a bottom tab bar on phones (under 600 px), a left rail on tablets (600 to 1023 px), and a
side nav on desktops (1024 px and up). The interface is in English and Brazilian Portuguese. The
language comes from `?lang=`, then from the stored choice, then from the browser.

## Mochi Home on the web (short version)

| Pi | Web |
|---|---|
| Wake phrase "Oi, Mochi" | **Start session** (sends `woken_by` in the UI language, so Mochi greets in it) |
| "tchau Mochi" / `bye` | **Stop session** (the face says bye for 2 s, then a "Session saved" card) |
| Face modes `sleeping`, `waking`, `awake`, `hearing`, `thinking`, `speaking`, `bye` | The same face (an inline SVG). The modes come from the session state, the browser's microphone level and Mochi's voice level. |
| Moods | Worked out in the browser: `happy` after Start, `curious` with a hint, `proud` when a word reaches `ASSISTED`, `excited` on `REINFORCED`, `oops` on an error, `sleepy` after 5 quiet minutes |
| `word` + `note` | The HintCard: the word, "English · adiar", the example, and a countdown |
| Volume `pop` | The "Mochi's voice" slider, with the same pop badge |
| `online: false` | An offline banner and a greyed face |
| Describe & Guess, tap and long press, temperature, voices | **Not built** (see below) |

## Microphone and HTTPS

On every load the app asks for the microphone first, in parallel with the check that reaches the
backend, so the browser asks on the first visit. Browsers allow the microphone only on `https://`
pages (`localhost` counts as secure). When the microphone cannot be used, the app says why: the page
is not secure, the browser cannot use a microphone, access is blocked, the page is inside another app,
there is no microphone, or the microphone is busy. Each reason has its own fix. "Continue without
microphone" enters the app with Start disabled. Mochi only hears while a session runs. Closing the
tab during a session stops it (`sendBeacon`), but locking a phone or switching apps does not.

## Run

```bash
cd apps/web
npm ci
npm run dev                                            # http://localhost:5173; /api, /ws, /healthz go to :8000
MOCHI_BACKEND_URL=http://<host>:8000 npm run dev       # a backend somewhere else
```

`scripts/start-dev.sh` from the repo root starts the backend on `:8000` with fake Agora, and this app
with it.

**Without a backend:** open `http://localhost:5173/?mock=1`. The mock backend runs in the page and
plays the AGENTS.md demo for the stored user. Mochi greets you, then shows **postpone** (adiar),
**umbrella** (guarda-chuva) and **queue** (fila), and marks postpone "Used with help". Past sessions
are pre-filled so that Digest and Analytics have data. Nothing leaves the browser.

## Tests

```bash
npm test              # every pure module (src/lib) and every component (renderToString); no browser, no network
npx tsc --noEmit
npm run build         # type-check + production build into dist/
```

The tests use Node's own test runner with `tsx` (the only dev dependency added). The events test
reads `packages/contracts/examples/events/*.json` from the repository.

## Docker

```bash
docker build -t mochi-web apps/web
docker run --rm -p 8080:8080 -e BACKEND_URL=https://<backend> mochi-web          # http://localhost:8080
docker run --rm -p 8080:8080 -e BACKEND_URL=http://host.docker.internal:8000 \
  --add-host=host.docker.internal:host-gateway mochi-web                          # a backend on this machine
```

nginx serves the build and proxies `/api/*`, `/ws` and `/healthz` to `BACKEND_URL`, so the browser
only talks to its own origin. `/web-healthz` is the container's own health check. `PORT` defaults to
8080. `BACKEND_HOST` defaults to the host of `BACKEND_URL`, and nginx sends it as `Host` and as SNI.
nginx resolves the backend's name once, at start, so a `BACKEND_URL` whose name does not resolve stops
the container from starting.

## Render

`render.yaml` has a second service, `mochi-web`: a Docker web service built from
`apps/web/Dockerfile`, with health check `/web-healthz`. After the backend's first deploy, set
`BACKEND_URL` by hand to its `https://` URL, with no trailing slash. Render gives `mochi-web` its own
public `https://` URL, and that is the address to open on phones. Both services are on the free plan
and sleep after 15 minutes. While the backend wakes, the app shows "Mochi is waking up…" (for up to a
minute).

## Not built

- **Describe & Guess in a web session.** The secret word goes only to the device's connection, and a
  web session has none. This is an open decision. If a round runs anyway, the app shows only its
  public line.
- **Mochi's temperature, voice enrolment and the tap/long press**, which are Pi-only.
- **Training does not change `learning_state`.** Its progress stays on this device. `USED_INDEPENDENTLY`
  is still an open decision (D-42).
- **Sign-in.** The user id is kept in `localStorage`. If the backend loses it (no database and a
  restart), the app asks for the name again.

The contract with the backend is THE SHARED CONTRACT in `docs/DECISIONS.md` D-42 (AGENTS.md 6.6).
For the code, see `CODE_GUIDE.md`. For the rules for agents, see `AGENTS.md` in this folder.
