# Latency test plan: arms, protocol, pass/fail

Goal: measure each latency lever **apart from production** and compare response time, correctness and
cost per arm. The arms are `config/presets/*.env`, and their README gives the expected savings.
Nothing here changes the Render service.

## Rules

- **Never touch production during a test.** Do not use channel `mochi-demo`, the Render URL, the
  production `DATABASE_URL` or the production keys. `scripts/start-test-backend.sh` forces all of
  this and refuses a Render URL or `mochi-demo`.
- **Only stop agents you started.** Stop your own session with `POST <test-url>/api/sessions/demo/stop`.
  Never call Agora's `/leave` on an agent you did not start, and never one in `mochi-demo`.
- One session per arm, with the same script, the same two voices and the same room each time.
- At least **10 spoken turns** per arm. `latency-compare.sh` warns below 10.
- Wait until Mochi has finished speaking before pressing Stop. A turn cut off by Stop is marked
  `interrupted` and is not counted.

## Arms

| Arm | Preset | What changes |
|---|---|---|
| PROD | `prod` | nothing (baseline, run first and again last if time allows) |
| SAFE | `safe` | drop stale turns, character hedge 1.0 s |
| ARES | `ares` | ears: ARES `en-US,pt-BR` + 24 keywords |
| CARTESIA | `cartesia` | voice: Cartesia sonic-3.6 |
| STREAM | `stream` | streamed free-chat replies |
| LIKELY | `likely` | SAFE + ARES + CARTESIA |
| STRETCH | `stretch` | LIKELY + STREAM + end of speech 480 ms |

## Isolation: how the test backend is set up

`scripts/start-test-backend.sh <preset> <https-tunnel-url>` runs the backend **on this laptop**. It loads
`.env`, then `prod.env`, then the preset, and only then forces these settings, so no preset can undo them:

| Setting | Test value | Why |
|---|---|---|
| `MOCHI_AGORA_MODE` | `real` | real Agora agent, real ears and voice |
| `MOCHI_CHANNEL` | `mochi-test` (or `$MOCHI_TEST_CHANNEL`, never `mochi-demo`) | its own Agora channel |
| `MOCHI_PUBLIC_URL` | the tunnel URL (https, not onrender.com) | Agora calls this laptop |
| `DATABASE_URL`, `MOCHI_LOCAL_DATA` | empty | **memory only**. Real mode refuses the local JSON file (`settings.py`), and the production database is never touched. Saved words are lost at exit. |
| `MOCHI_TURN_KEY` | fresh random per run, never printed | Agora gets it in the start request |
| `MOCHI_DEVICE_KEY` | `$MOCHI_TEST_DEVICE_KEY`, else `.local/test-device-key` (git-ignored, 0600, created once) | the Pi needs the same key to get the game's secret word |
| `MOCHI_ENABLE_DEV_ROUTES` | `true` | `scripts/say.sh` against the test backend |

The log is kept in `.local/latency/<preset>-<UTC time>.log`. It has the `agent_started` line (the agent
id) and the `model_usage` lines for cost.

**Pointing the Pi at the test backend (Matheus's config: do this on the Pi, only for the test, then
undo).** Put this in `hardware/pi-bridge/config/mochi.local.toml` (not in git), not in the shared
`mochi.toml`:

```toml
[backend]
kind = "mochi_backend"
mochi_backend_url = "https://<tunnel>.trycloudflare.com"   # the test URL, not Render
keep_awake_s = 0                                            # a laptop backend does not sleep
```

In the Pi's `.env`, set `MOCHI_DEVICE_KEY=<contents of .local/test-device-key>`. Copy it by hand, and
do not paste it into chat or a commit. The Pi gets the channel (`mochi-test`) from `GET /state`, so
nothing else changes. Restart: `systemctl --user restart mochi`. **After the tests**, delete
`mochi.local.toml` (or point it back at Render), restore the production device key and restart.

**Alternative: a second Render service** built from this branch, e.g. `mochi-backend-test`, with its own
channel, keys, no `DATABASE_URL`, and the preset's variables. It is closer to production's network
path (Render in Oregon), but it needs a push of this branch and the owner's OK to create the service.
It is not created by anything here. The free plan sleeps after 15 minutes: run `scripts/keep-warm.sh
<its-url>` during the test.

## The script (same every run, about 3 minutes)

Two people, Ana and Ben, with the same voices every run. Leave about 3 s between lines and let Mochi
finish speaking.

1. Wake: `Oi Mochi` (Mochi greets and asks what to do), then choose company mode (Companhia) with the same words in every run.
2. Ana: `I need to adiar my meeting tomorrow.` → hint **postpone**
3. Ben: `Oh, why? What's going on?`
4. Ana: `Right, I'll postpone it to Friday.`
5. Ana: `I forgot my guarda-chuva at the office.` → hint **umbrella** (lines 2-5 are the approved four-line script; `while_shown`)
6. Ana: `Oi Mochi, what's the word for fila?` → Mochi says it (queue) and shows it
7. Ben: `Oi Mochi, what's the capital of Australia?` (a free-chat question; Mochi answers)
8. Repeat lines 6-7 with small changes (`what's the word for recibo?`, `Mochi, tell me a fun fact about
   Brazil.`, …) until the arm has **at least 10 spoken replies**.

Spoken turns: lines 6-8 and the greeting follow-up. Silent turns: lines 2-5.

### ARES accuracy block (ARES, LIKELY, STRETCH, and PROD as the comparison)

The script says each demo word once, but the go/no-go needs 10/10. In the same session, after the
script, Ana says each demo sentence **10 times**, alternating `adiar` and `guarda-chuva`, with a filler
line from Ben in between (`Okay.` / `Really?`). Wait about 10 s after each hint so it leaves the screen
(`while_shown` shows nothing while a hint is up, and never the same word twice in a row). Score it from
the **transcript**, not only from the hint. The backend's `turn` log line has the heard `text`. Agora
sends everything said since Mochi last spoke as one message, so read only its last sentence:

```bash
grep '"event": "turn"' .local/latency/ares-<time>.log | tail -40
```

The opening `Oi Mochi` (step 1) is matched **offline on the Pi**, so ARES never hears it. What ARES
changes is the mid-session `Oi Mochi, …` lines (6-8): count each as answered (a `decision` line with
SPEAK / `asks_mochi`) or missed, per arm.

## Steps per arm

```bash
# terminal 1: public URL
scripts/tunnel.sh                                    # copy https://xxxx.trycloudflare.com
# terminal 2: backend for the arm
scripts/start-test-backend.sh prod https://xxxx.trycloudflare.com
# Pi: mochi.local.toml points at the test URL (above); restart the Pi service once
# run the script by voice through the M1A; wait for the last reply to finish
curl -X POST https://xxxx.trycloudflare.com/api/sessions/demo/stop     # or "tchau Mochi"
grep agent_started .local/latency/prod-*.log | tail -1    # the agent id
# Ctrl-C the backend, start the next arm with the same tunnel URL
```

After all arms (turns are readable only after the agent left):

```bash
scripts/latency-compare.sh PROD=<id> SAFE=<id> ARES=<id> CARTESIA=<id> STREAM=<id> LIKELY=<id> STRETCH=<id>
scripts/cost-estimate.sh PROD,openai,minimax,<id>,.local/latency/prod-<time>.log \
                         ARES,ares,minimax,<id>,.local/latency/ares-<time>.log ...   # one per arm
scripts/agora-turns.sh <id>      # one arm's turns in detail, if something looks odd
```

Intelligence regression (no voice, real model, about 1 minute each). Run it **3 times** on this branch
and 3 times on a fresh `main` checkout, and report each as a **range** (min-max pass rate). One run is
noise. `.env` must have `MOCHI_MODEL_NAME=gpt-5.4-mini` and `MOCHI_MODEL_REASONING_EFFORT=none`. The hint
model is the same in every arm, so this is not run per arm.

```bash
for i in 1 2 3; do scripts/eval-intelligence.sh | tail -1; done
```

## Pass / fail

**ARES** (go only if all hold):
- Each demo word, `adiar` and `guarda-chuva`, is written correctly **10/10** in the accuracy block,
  with real voices through the M1A, and each fires its hint.
- Mid-session `Oi Mochi, …` lines are answered no worse than PROD (misses counted as above).
- Portuguese sentences (`Você viu o jogo ontem?`, `Como se diz umbrella em português?`) are
  transcribed in Portuguese, not dropped or anglicised.
- Median `asr_ttlw` delay ≤ about 1.1 s.
- Background check (D-36): about 2 minutes of faint background talk (a recording at low volume, nobody
  near the M1A) produces **no** lexicon hint. With `MOCHI_ASR_LEXICON_WORDS=true` the 20 lexicon words
  are keywords, and naming them made gpt-4o-transcribe hear them.

**CARTESIA**: a human listens through the M1A to these three lines in both voices (MiniMax in PROD,
Cartesia in CARTESIA) and judges whether each is acceptable. Ask Mochi by voice to say them, or send them with
Agora's `POST .../agents/<agent id>/speak`, only on the test agent you started:
`Hi! I'm Mochi. Let's practice together.` / `Oi! Eu sou a Mochi. Vamos praticar juntos.` /
`You can say: guarda-chuva.` The language is fixed to `en`, so the Portuguese line is the risk.
Mochi must also never go silent (a wrong voice id fails with no error).

**STREAM**:
- The round's secret word is never spoken during a game round. Start one with `let's play`, then ask
  `Oi Mochi, what's the word?`.
- `[quiet]` and other bracket tags are never spoken.
- With the flag off, the output is identical to PROD (the unit tests cover this; listen once anyway).

**Eval**: no new failures beyond the fresh `main` baseline range.

**Hint correctness (every arm)**: both demo hints (postpone, umbrella) fire in the approved script under
`while_shown`, are saved for Ana only, and plain lines show nothing.

## Results (fill in)

| Arm | n spoken / silent | e2e p50 / p95 (ms) | asr_ttlw p50 | llm_ttft p50 | tts_ttfb p50 | both demo hints | adiar / guarda-chuva x/10 | Oi Mochi misses | listening OK | secret / [quiet] spoken | eval range | cost / 10 min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PROD | | | | | | | | | n/a | n/a | | |
| SAFE | | | | | | | | | n/a | n/a | | |
| ARES | | | | | | | | | n/a | n/a | | |
| CARTESIA | | | | | | | | | | n/a | | |
| STREAM | | | | | | | | | n/a | | | |
| LIKELY | | | | | | | | | | n/a | | |
| STRETCH | | | | | | | | | | | | |

## Open unknowns this test should settle

1. **Does `asr_ttlw` include the end-of-speech wait?** Compare STRETCH (480 ms) with LIKELY (600 ms):
   if it is included, `asr_ttlw` drops by about 120 ms. The two readings of the baseline (2.9-3.2 s
   vs 3.6-3.9 s to first sound) depend on this.
2. **Pi transport and playback are not in Agora's e2e** (there is no `transport` segment). Mochi's
   real delay is e2e plus about 0.25 s (estimate). To measure it, film one reply and count frames
   from the end of speech to the first sound.
3. Does streaming save 0.15-0.3 s or 0.4-1 s? Compare `llm_ttft` in STREAM with PROD on the free-chat
   lines only.
4. Which turn the p95 was, and whether golden turn 10's unexplained +1.35 s happens again. Match
   `turn_arrived` / `reply_first_byte` in the log with Agora's turns.
5. How Cartesia is billed under Agora's managed key (`config/prices.json` marks it unverified).
