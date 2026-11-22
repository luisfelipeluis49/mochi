# Real turn and Portuguese: runbook

Goal: two people, two languages, one mic. Ana (Portuguese at home, practising English) and Ben (English at
home, practising Portuguese) talk to each other; Mochi helps whoever is stuck.

Everything below runs against the **Render** service (`MOCHI_PUBLIC_URL` points there, so Agora's cloud calls it).
Calling Start on a local backend would still send the turns to Render, which is not capturing: you would get silence
for a misleading reason. Each session uses free Agora minutes (300 free), so Stop after every run.

## 0. What was checked offline
- The request body Agora documents for custom LLM (extra top-level fields, message metadata, no `stream`) returns a
  200 SSE stream (`tests/integration/test_gateway_http.py`).
- Per-turn language: Ben saying `Eu esqueci meu umbrella no escritório.` gets the hint `guarda-chuva`; pure
  Portuguese stays quiet; `Ben, como se diz recibo?` still gives Ana `receipt`.

## 0b. The test client
`scripts/test-client/index.html` is a stand-in for the Pi bridge, not the product web app (that is Tasnim's).
It loads the Agora Web SDK `AgoraRTC_N-4.24.10.js` from `download.agora.io` (the version the Agora quickstart shows;
not confirmed to be the newest) and uses only calls from the Agora docs: `createClient`, `join`,
`createMicrophoneAudioTrack({AEC, AGC, ANS})`, `publish`, `createBufferSourceAudioTrack` +
`startProcessAudioBuffer`. It is a new dependency (a CDN script, nothing installed). The echo flags do not prove
the M1A will not hear itself (AGENTS section 12, item 3).

## 1. The question to settle first
Does Deepgram `nova-3` with `language: multi` transcribe English and Portuguese in one Agora session, and keep
`adiar` / `guarda-chuva` (and English words inside Portuguese)? The Agora and Deepgram docs disagree. Only a real
session answers it. Design rule until then: do not assume either result.

Outcomes:
- **Works:** one agent per session, `multi`. Nothing else to change.
- **Mangles switched words or drops Portuguese:** fall back to one ASR language per session, chosen at Start. The
  docs say ASR cannot change while the agent runs, so switching language means Stop then Start (restart cost
  untested).

## 2. Run
1. Headphones on (laptop speakers would play Mochi's voice back into the mic as a new turn).
2. Start the session on Render: `curl -X POST https://mochi-backend-6e2a.onrender.com/api/sessions/demo/start`.
3. Run `scripts/test-client.sh`, open http://localhost:5173, press "Join and send microphone" and speak the
   sentences below. The page reads Render's device state and joins the channel as the Pi (uid 1001). To compare ASR
   settings on identical audio, record each sentence once and use "Play clip once" instead of the microphone.
4. Read the turns: Render dashboard logs, or `list_logs` through the Render tool; look for the `turn`, `decision`
   and `event_published` lines.
5. Stop: `curl -X POST https://mochi-backend-6e2a.onrender.com/api/sessions/demo/stop`.

## 3. Sentences to record (write down the logged transcript for each)
English, Ana (as in AGENTS section 2):
1. `I need to adiar my meeting tomorrow.` (expect a hint: postpone)
2. `I forgot my guarda-chuva at the office.` (expect: umbrella)
3. `Did you watch the match yesterday?` (a plain sentence: expect no hint)

Portuguese, Ben (proposed):
4. `Eu preciso postpone minha reunião amanhã.` (expect a hint for Ben: adiar)
5. `Eu esqueci meu umbrella no escritório.` (expect: guarda-chuva)
6. `Você viu o jogo ontem?` (plain: expect no hint)

Questions (proposed):
7. `Ben, como se diz recibo?` (Ana asks; expect a hint for Ana: receipt)
8. `Como se diz umbrella em português?` (Ben asks; expect a hint for Ben: guarda-chuva)

Voice (one line each, to check the text-to-speech):
9. `Oi Mochi, what's the word for fila?` (Mochi answers in English)
10. `Oi Mochi, como se diz receipt?` (Mochi answers in Portuguese; MiniMax voice quality is untested)

## 4. For the team to confirm (the demo script)
The walkthrough in AGENTS section 2 is English only. For two languages, a proposal:
1. Observe: Ana and Ben talk (Ana English, Ben Portuguese), Mochi stays quiet.
2. Help: Ana says sentences 1 and 2; Ben says sentences 4 and 5. Each hint is saved for the person who needed it.
3. Remember: Ana's phone shows `umbrella - Hint shown`, `postpone - Used with help` (she said it right
   after the hint); Ben's shows `guarda-chuva` and `adiar` the same way.
4. Review (Papear, D-44; replaces the two Play rounds, which were removed with the game, D-43): Ana starts
   a review on her phone. Mochi asks for `umbrella` through its meaning, she says it, and the card reads
   `Recalled in a review`.
5. The company sees (D-45): `GET /api/companies/demo/insights?viewer=ana` lists `postpone` and `umbrella`
   among the expressions the team needed, with no name next to them.

Questions for the team: are these the right sentences? Who says what in the real demo? Nobody has done a
review by voice yet (AGENTS 12.5).

## Database (Postgres on Render)

- **Database:** `mochi-db`, free plan, Oregon, Postgres 17, workspace `mochi`. Created **2026-11-21**; a free
  database **expires 2026-12-21** and Render deletes it about 14 days later (2027-01-04) unless upgraded.
  Upgrade it in the Render dashboard (mochi-db > Settings > Instance type) before 2026-12-21.
- **Connect the service:** set `DATABASE_URL` on `mochi-backend` to the database's **Internal Database URL**
  (dashboard > mochi-db > Connections). This redeploys the service and empties its memory once. Check
  `GET /readyz`: `"storage": "postgres"`. Logs: `storage_ready` at start; `storage_unavailable` means it fell back
  to memory (expired, wrong URL, or Postgres down); `storage_write_failed` is one lost write.
- **Look at the data:** `psql "<External Database URL>"` needs your IP in the database's allow list. Tables:
  `users`, `learning_events`, `voices` (voiceprints are biometric: do not paste them anywhere).
- **Reset:** `POST /api/demo/reset` clears learning events only. Users and voices stay.
- **Moving to a new database** (after expiry): `pg_dump` the old one before it is deleted, or start empty;
  tables and the two demo users are created on the first start.
