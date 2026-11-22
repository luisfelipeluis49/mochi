# apps/web — Mochi's screens (owner: Tasnim)

One React + TypeScript (Vite) app with three views. It shows what the gateway sends. It never decides who sees what, and it has no AI, speech, or storage.

**Company version (Nov 2026):** Mochi joins meetings. On the Pi you wake it with "Hi Mochi"; on a phone you tap **Start session** and Mochi takes part live through the phone, with the same behaviour as the Pi's screen. After the meeting, the **Analytics** tab shows how it went and which words to learn. Mochi's screen (`/home`) and the projector are unchanged. Data still marked PROPOSED (the session summary) is in `PROPOSAL_contracts_v0.5.md`.

| URL | What it is |
|---|---|
| `/` | **Start page**. Each phone belongs to one person: once a phone has opened its owner's link (`/m?user=tasnim`), `/` goes straight to that person's page. Otherwise it explains how to open your link, plus links to Mochi's screen and the projector. No list of people to choose from |
| `/home?device=home_pi_01` | Mochi's 3.5-inch screen: **who is talking** (name badge in the corner, like the device's `face.html`), face (cream), "What do you want to do today?", hints with 1–3 options and who they are for, what Mochi says, the game. Tap anywhere, or hold (600 ms) |
| `/m?user=ana` · `/m?user=ben` | **Company version: a person's phone, two tabs at the bottom (Session · Analytics)**, switched without reloading. **Session**: *Start session* (on the Pi you say "Hi Mochi"; here you tap) and Mochi joins the meeting **live** through the phone: the phone's mic listens, Mochi speaks through the phone (its own Agora session, D-41), and the middle of the screen behaves like Mochi's own screen: face while listening, the word (with meaning and example) when someone gets stuck, what Mochi says, who is talking. *Stop session*. No recording and no game. The mic needs **https** (Vercel or ngrok); with `?mock=1` no mic is used |
| `/m/analytics?user=ana` | **Analytics** tab: **Your progress** (new words, used with help, recalled in a game, minutes), **Your last session** (strengths, to review, new expressions, next step), **Sessions** (minutes per session), **Words to learn** cards. During a session, a note that its analytics come when it ends. The old `/me` address opens this tab |
| `/audience` | The projector. Never shows the secret word before `ROUND_RESULT` |

Add to any URL: `?mock=1` (replay the demo without a backend), `&people=tasnim,matheus` (your names in the mock demo; Mochi shows who is talking), `&speed=4` (faster mock), `&debug=1` (last ten events), `&lang=pt-BR` (Portuguese text), `&projector=1` (a phone page drawn large, for the projector).

## Run

```bash
cd apps/web
npm install
npm run dev          # http://localhost:5173 — forwards /api and /ws to the backend on :8000
npm test             # logic tests, no browser needed (Node 22.6+)
npm run build        # type-check + production build into dist/
```

With this repo's backend (from the repo root, in Git Bash on Windows): `scripts/start-dev.sh` starts it on `:8000` with fake Agora. Then `npm run dev` here, open `http://localhost:5173/m?user=ana`, and send a sentence with `scripts/say.sh "I need to adiar my meeting tomorrow"`.

Without the backend: open `http://localhost:5173/home?mock=1`, `http://localhost:5173/m?user=ben&mock=1` and `http://localhost:5173/m?user=ana&mock=1`.
With a backend somewhere else: `VITE_BACKEND_URL=https://<public-backend> npm run dev`, or `MOCHI_BACKEND_URL=http://<host>:8000 npm run dev` to change the dev forwarding target.

## Hosting (so phones, the Pi and the projector open one link)

The web app is a set of static files (`npm run build` → `dist/`). It talks to the backend through
`VITE_BACKEND_URL`, read **at build time**. `vercel.json` in this folder is ready for Vercel:

1. On vercel.com: **Add New → Project → Import** `luisfelipeluis49/mochi`.
2. **Root Directory:** `apps/web` (important: not the repo root).
3. **Environment Variables:** `VITE_BACKEND_URL` = `https://mochi-backend-6e2a.onrender.com`
   (the Render backend; no slash at the end).
4. **Deploy.** Vercel gives a `https://….vercel.app` address. Pages: `/home?device=home_pi_01` (Pi kiosk),
   `/m?user=ana` (Session) and `/m/analytics?user=ana` (Analytics), `/m?user=ben`, `/audience`.

The backend allows any origin (`MOCHI_CORS_ORIGINS=*`), so no backend change is needed. Every push to
`main` redeploys the web app; pull requests get their own preview link.

## The mock demo (`?mock=1`)

Start → "Oi, Mochi!" (mode question) → Companhia: Sophie gets *me queimei · tomei muito sol*, Ana gets *postpone*, Sophie asks for "sunscreen" and Mochi says *Protetor solar.* out loud, Ana gets *umbrella* → Jogar: Ana describes *umbrella*, Sophie guesses, Mochi says *Correct! Sophie, your turn to describe.* → Stop → each phone shows its progress, its summary, its sessions (with one fake session from yesterday) and its word cards.

See `CODE_GUIDE.md` for every file, grouped by language.

## Report

**Tested:** 60 logic tests (`npm test`) cover:
- duplicate events ignored, hint expiry, hint options, session summaries;
- the analytics numbers (words by step, minutes added up, session order, bar sizes);
- the Session tab follows Mochi's own screen (face, hint with meaning and example, Mochi speaking, no game on the phone); the tabs keep the person and options;
- the mode question winning over Mochi speaking it;
- the full round (reveal, guessed, skipped, no double send, result then back to the face);
- that the mock gives the secret word only to Mochi's screen, and words and summaries only to their owner.

Also driven in headless Chrome at 480×320, 390×844 and 1280×720 through the whole mock demo. Ana's phone ends with *umbrella: Recalled in a game* and *postpone: Used with help*. Sophie's ends with *protetor solar* and *me queimei*, her 24-minute summary, and 39 minutes over 2 sessions. The phones show no hint and no game button. The projector never shows the secret during the round.

**Not tested here:** `npm install`/`vite` itself (no network in the build sandbox; bundled with esbuild instead), the real backend, and the real Pi screen.

**Dependencies:** react, react-dom; dev: vite, @vitejs/plugin-react, typescript, @types/react, @types/react-dom, @types/node. Tests use Node's built-in runner.

**Fixed in this round:**
- Hints are timed from the server's own times (`expires_at − emitted_at`), counted on the device from arrival, so a Pi with a wrong clock no longer hides them (integration review item 6).
- The demo's second person is `SECOND_USER` in `src/lib/who.ts` = `ben`, the backend roster; the mock and links follow it.
- "Start a game" is back on the Operator's phone (`/m`), until the backend can start a round by voice.
- `vercel.json` + the Hosting section above.
- `src/lib/contract.test.ts` checks the app against `packages/contracts` on every CI run.

**Open, for a human to decide:**
1. **Contract v0.5 proposal**: the modes `choosing` and `practice`, the speak reason `practice_partner`, the event `session.summary.created`, and hint options with " · ". See `PROPOSAL_contracts_v0.5.md`.
2. **"Who said what"**: the new vision needs it. It's a backend and audio question; the screens already use `target_user_id`.
3. `packages/contracts` doesn't exist yet. `src/contracts.ts` is a stopgap copy; lines marked `PROPOSED v0.5` are the proposal.
4. **History for the analytics.** The phone only knows what it received while open. On connect the server should re-send this person's words and **all their past session summaries** (and, to Mochi's screen, the active secret word). Otherwise the progress numbers start from zero after a reload.
5. **The game starts by voice** ("Bora jogar!"), so the "Start a game" button was removed from the phone. The backend must start the round itself.
6. **Reset** sends no event that clears words or summaries; reload the pages after a reset.
7. **"Speaking" duration** is estimated (≥ 2.5 s, ~85 ms per character), because `Speak` has no duration.
8. Touch reliability on the real 3.5-inch panel (AGENTS.md §12, item 4).
