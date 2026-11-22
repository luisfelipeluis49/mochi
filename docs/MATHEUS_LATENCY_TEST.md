# Latency test for Matheus: `main` against `latency-performance`

You do **one** thing: speak to Mochi when Claude says READY. Your Claude does everything else (backends,
tunnel, Agora, logs, tables). Read Part 1 (about 5 minutes of your own setup), then give your Claude the
prompt in Part 2.

Nothing here touches production: no Render service, no `mochi-demo` channel, no production database.
The test backend runs on your laptop on its own channel `mochi-test`, with memory-only storage.

## Part 1: what you do

### One-time setup (before the session)
1. **Laptop:** `git` , `uv` (https://docs.astral.sh/uv/) and `cloudflared`
   (https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) installed.
2. **Secrets:** Luís sends you his `.env` through a private channel (not chat, not git, not an issue). Put it at the
   repo root as `.env`. It is git-ignored. Do not paste it anywhere, including to Claude: Claude reads it
   from the file and must never print it.
3. **Clone and branch:**
   ```bash
   git clone https://github.com/luisfelipeluis49/mochi.git && cd mochi
   git checkout latency-performance
   ```
4. **Pi (once, then undo at the end).** Ask Claude to run Part 2 first; it generates the device key and
   the tunnel URL, then it tells you the two values to put on the Pi:
   - `hardware/pi-bridge/config/mochi.local.toml` (not in git):
     ```toml
     [backend]
     kind = "mochi_backend"
     mochi_backend_url = "https://<tunnel>.trycloudflare.com"   # Claude tells you this
     keep_awake_s = 0
     ```
   - the Pi's `.env`: `MOCHI_DEVICE_KEY=<contents of .local/test-device-key on your laptop>` (copy by hand).
   - `systemctl --user restart mochi`.
   The Pi gets the channel (`mochi-test`) from the backend, so nothing else changes. Keep the tunnel
   running for the whole session: the URL stays the same between arms, so you set the Pi up **once**.
5. **Pi on Wi-Fi** as in the demo, 5 GHz, Wi-Fi power-save off. Same room, same two voices, same
   distance to the M1A for every arm.

### During the session (your whole job)
- Claude says **`ARM <n> of <total>: <name>. READY.`** Then you speak the script below, with about 3 s between lines
  and waiting until Mochi has finished each reply. Two people (Ana, Ben) or one person doing both voices.
- When you finish the last line, say **`done`** to Claude. Claude ends the session, switches the backend to the
  next arm and says READY again. Between arms you do not touch the Pi.
- If anything is odd (Mochi silent, wrong voice, a hint that should not appear) tell Claude in one
  sentence. It records it as a note on that arm.

### The script (same every arm, about 3 minutes)
1. Say `Oi Mochi`. Mochi greets. Choose company mode (Companhia) with the same words every time.
2. Ana: `I need to adiar my meeting tomorrow.` → hint **postpone** on the screen
3. Ben: `Oh, why? What's going on?`
4. Ana: `Right, I'll postpone it to Friday.`
5. Ana: `I forgot my guarda-chuva at the office.` → hint **umbrella**
6. Ana: `Oi Mochi, what's the word for fila?`
7. Ben: `Oi Mochi, what's the capital of Australia?`
8. More of the same kind until there are **at least 10 spoken answers**: `Oi Mochi, what's the word for
   recibo?`, `Mochi, tell me a fun fact about Brazil.`, `Oi Mochi, how do you say umbrella in Portuguese?`,
   `Oi Mochi, what's two plus two?` …
9. **Accuracy block, only when Claude says "accuracy block" for the arm:** Ana alternates 10 times
   `I need to adiar my meeting tomorrow.` and `I forgot my guarda-chuva at the office.`, with Ben saying `Okay.` or
   `Really?` in between. Wait about 10 s after each hint so it leaves the screen.
10. Portuguese check (accuracy-block arms): `Você viu o jogo ontem?` and `Como se diz umbrella em português?`.
11. *(Was the game check. The game was removed on 2026-11-21, DECISIONS D-43: skip this step.)*
12. **Listening check, CARTESIA / LIKELY / STRETCH arms only:** Claude will tell Mochi's own lines to
    listen for: `Hi! I'm Mochi. Let's practice together.`, `Oi! Eu sou a Mochi. Vamos praticar juntos.`,
    `You can say: guarda-chuva.` Say `good`, `bad` or `odd` for each. That is the only subjective part.

### After the session
Undo the Pi: delete `mochi.local.toml` (or point it back at Render), restore the production `MOCHI_DEVICE_KEY`, restart the
service. Send Luís the `RESULTS.md` summary your Claude prints (no secrets in it).

---

## Part 2: the prompt for your Claude

Paste everything between the lines into Claude Code, opened at the repo root on branch `latency-performance`.

------------------------------------------------------------------------------------------------

You are running a latency A/B test for the Mochi project. I (Matheus) only speak to the Mochi device
when you say READY. You do everything else. Read `docs/LATENCY_TEST_PLAN.md` and `config/presets/README.md`
first; this prompt is the procedure and wins where they differ.

**Hard rules**
- Never print, log, paste or commit a secret. `.env` holds keys: read it only through the scripts, never `cat` it, and
  never put a key in a command line you show me. Do not echo `.local/test-device-key`; tell me the file path and I copy it myself.
- Never touch production: not the Render service or its dashboard/API, not the channel `mochi-demo`, not the
  production database. `scripts/start-test-backend.sh` refuses those; do not work around it.
- Agora: only stop the session on YOUR test backend (`scripts/finish-arm.sh`). Never call Agora's `/leave` on any agent you did not
  start. If `GET /agents` shows an agent you did not start, leave it alone and tell me.
- No pushes, no PRs, no commits. Results stay in `.local/latency/` (git-ignored). Edit no repo files.
- Ask me before installing software. Do not run whole-tree formatters.

**Setup (once)**
1. `git fetch origin && git checkout latency-performance && git pull`. Check `uv`, `cloudflared` and `.env` exist (names only,
   no contents). Check `.env` has non-empty `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `AGORA_REST_KEY`, `AGORA_REST_SECRET`, `MODEL_API_KEY`
   by testing each with `grep -q '^NAME=.\+' .env` only.
2. Baseline checkout for `main`: `git worktree add ../mochi-main origin/main` (detached). Copy `.env` into it only if the scripts need it (they read
   the repo-root `.env` of THIS checkout, so you normally do not).
3. Run `make verify` here once; report the result. Do not continue if it fails.
4. Start the tunnel in the background and keep it running for the whole session: `scripts/tunnel.sh`. Read the
   `https://….trycloudflare.com` URL from its output. Call it `$URL`.
5. Generate the device key by starting the first arm (it is created at `.local/test-device-key` on first run).
   Then tell me exactly: (a) the URL for `mochi.local.toml`, (b) the path of the key file, (c) the restart command. Wait for me to say
   `pi ready`. Verify the Pi connected by watching the backend log for the first `agent_started` after I say "Oi Mochi".

**Arms and order** (one session per arm; the SAME tunnel URL for all)
Full run (9 sessions, about 45 minutes): `MAIN`, `PERF-prod`, `SAFE`, `ARES`, `CARTESIA`, `STREAM`, `LIKELY`, `STRETCH`, `MAIN` again.
- `MAIN`: backend code from main: `MOCHI_BACKEND_DIR=$(pwd)/../mochi-main/services/backend scripts/start-test-backend.sh prod $URL`
- `PERF-prod`: this branch with the production preset (the control): `scripts/start-test-backend.sh prod $URL`
- `SAFE`, `ARES`, `CARTESIA`, `STREAM`, `LIKELY`, `STRETCH`: `scripts/start-test-backend.sh <lowercase name> $URL`
If I say "quick", run only `MAIN`, `LIKELY`, `STRETCH`, then `MAIN` again. The second `MAIN` shows how much Agora/network drift there was
between the first and last run: report the difference.
"Accuracy block" applies to `MAIN`, `PERF-prod`, `ARES`, `LIKELY`, `STRETCH`. The game check no longer exists (D-43).
The listening check applies to `CARTESIA`, `LIKELY`, `STRETCH`.

**Per arm (loop)**
1. Start the arm's backend in the background (one background process per arm). Wait until `$URL/healthz` returns 200 (poll, max 60 s;
   if the tunnel URL changed, stop and tell me).
2. Tell me: `ARM <n> of <total>: <name>. READY.` plus which extra checks apply (accuracy block, listening check, with the exact lines).
3. Wait for me to say `done`. While waiting, watch the arm's log (`.local/latency/<preset>-<time>.log`) for `agent_started` (session
   began) and for errors; tell me at once if the session did not start within 60 s of my "Oi Mochi".
4. When I say `done`: `scripts/finish-arm.sh $URL <that log file>` (stops the TEST session and prints `agent_id=…`). Record the label,
   agent id, log path and my notes. Stop that arm's backend process (only the one you started). Count spoken answers from the log; if fewer than
   10, tell me and ask whether to repeat the arm.
5. Next arm.

**After all arms** (turns are readable only after each agent left)
1. `scripts/latency-compare.sh MAIN=<id> PERF-prod=<id> SAFE=<id> ARES=<id> CARTESIA=<id> STREAM=<id> LIKELY=<id> STRETCH=<id> MAIN2=<id>`
   (omit missing arms). Warn about any arm with fewer than 10 turns.
2. `scripts/cost-estimate.sh` per arm as in `docs/LATENCY_TEST_PLAN.md` (for MAIN use the PERF-prod usage log: the model calls are identical and main
   does not log `model_usage`). State which prices are unverified.
3. Accuracy block: for each arm that had it, score `adiar` and `guarda-chuva` x/10 from the `turn` log lines, count `Oi Mochi` answered/missed,
   and the Portuguese check, as in the plan. Do not score from the hint alone.
4. Intelligence eval: `for i in 1 2 3; do scripts/eval-intelligence.sh | tail -1; done` on this branch, and the same from `../mochi-main`
   (its own `scripts/eval-intelligence.sh`, with the same `.env` values exported). Report each as a MIN-MAX range. It spends a little OpenAI money.
5. Write `.local/latency/RESULTS.md`: the results table from the plan filled in, one row per arm, then a short verdict:
   - For each lever: seconds saved (e2e p50 and p95 against `PERF-prod`, and `PERF-prod` against `MAIN`), whether correctness held (pass/fail rules in the plan),
     cost per 10 minutes against `PERF-prod`, and a go / no-go / needs-more-data.
   - Say what drift MAIN vs MAIN2 shows, so the team knows the noise level.
   - List unknowns the plan asks about (does `asr_ttlw` include the end-of-speech wait; Pi transport/playback is outside Agora's e2e).
   - No secrets. Print the summary for me to send to Luís.
6. Remind me to undo the Pi (`mochi.local.toml`, production device key, restart) and offer to remove the `../mochi-main` worktree
   (`git worktree remove ../mochi-main`) once I confirm.

If a step fails, show me the error (minus secrets), say which arm it was, and propose the smallest fix; do not improvise around the safety rules.

------------------------------------------------------------------------------------------------

## What the results will answer

- **Response time:** per-stage p50 and p95 from Agora's own turn data (`asr_ttlw`, `llm_ttft`, `tts_ttfb`, `e2e`) for spoken turns and silent
  (hint) turns separately, against `MAIN` and against `PERF-prod`.
- **Correctness:** both demo hints, ARES accuracy on `adiar` and `guarda-chuva`, `Oi Mochi` answered, Portuguese sentences, streaming leaks, the intelligence
  eval range.
- **Cost:** per 10 minutes, from the `model_usage` lines and agent minutes. Agora bills about $0.10 per agent minute after the free 300 minutes
  per month; the full run is roughly 40 agent minutes, so about $4 at most, usually free.
