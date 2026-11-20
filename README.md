# Mochi

Mochi is a small physical companion that helps **two people practice a language with each other**
(English and Brazilian Portuguese). It listens during a session they start, shows a one-word hint
when one of them gets stuck, hosts a short two-player game, and remembers the words each person
needed. Product and contracts: [`AGENTS.md`](AGENTS.md). This repository currently holds the
**backend**, the shared contracts and the scripts; the web app (`apps/web`) and the Pi bridge
(`hardware/`) are owned by other teammates.

```mermaid
flowchart LR
  M1A[M1A mic/speaker] --> Pi[Pi bridge]
  Pi -- audio --> Agora[Agora agent: STT + TTS]
  Agora -- "HTTPS: one turn" --> GW
  subgraph Backend [Backend: one process]
    GW[gateway] --> INT[intelligence: decide / handle / apply / words_for]
    INT --> GW
  end
  GW -- WebSocket events --> Home[Home view]
  GW -- WebSocket events --> Mobile[Mobile views]
  GW -- WebSocket events --> Aud[Audience view]
  Pi -- polls device state --> GW
```

## Quick start (fake Agora, 3 commands)

```bash
make -C services/backend install          # uv sync (needs uv: https://docs.astral.sh/uv/)
scripts/start-dev.sh                      # backend on :8000, MOCHI_AGORA_MODE=fake, dev routes on
scripts/smoke.sh                          # in another terminal: PASS/FAIL per demo step
```

Try it by hand: `curl -X POST localhost:8000/api/sessions/demo/start`, then
`scripts/say.sh "I need to adiar my meeting tomorrow"`, and watch events with
`uv run --project services/backend python scripts/watch_ws.py --as user=ana`.

## Dependencies and versions

Python 3.12, [uv](https://docs.astral.sh/uv/) 0.13.9 (locked in `services/backend/uv.lock`), FastAPI,
uvicorn, httpx, pydantic v2 + pydantic-settings, `agora-token-builder` 1.0.0. Dev: ruff, mypy (strict),
pytest, pytest-asyncio. Docker (optional) for the image. `jq` for `scripts/smoke.sh`.

**Version identification:** `GET /healthz` returns `{"status":"ok","version":"<git sha>"}`. The SHA is
the `GIT_SHA` build argument (`scripts/deploy.sh` passes `git rev-parse --short HEAD`); it reads `dev`
when run from source.

## Real Agora setup

1. In the Agora Console create a project with an App Certificate; create RESTful API keys.
2. Copy `.env.example` to `.env`; set `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `AGORA_REST_KEY`,
   `AGORA_REST_SECRET`, `MOCHI_TURN_KEY` (any long random string), and `MOCHI_AGORA_MODE=real`.
3. Speech vendors: `.env.example` already holds a working, key-free pair (Agora-managed deepgram ASR + minimax TTS). Otherwise set `MOCHI_ASR_VENDOR`, `MOCHI_ASR_PARAMS`, `MOCHI_TTS_VENDOR`,
   `MOCHI_TTS_PARAMS` (JSON objects; see `services/backend/src/mochi_backend/gateway/agora/VERIFIED.md`).
4. Give the backend a public HTTPS address: `scripts/tunnel.sh` (cloudflared or ngrok) or Render, and set
   `MOCHI_PUBLIC_URL` to it.
5. Optional: `MODEL_API_KEY` (+ `MOCHI_MODEL_BASE_URL`, `MOCHI_MODEL_NAME`) for words outside the built-in
   lexicon. Without it the rule-based cases (including both demo sentences) still work.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE` | - | Agora project (required when `MOCHI_AGORA_MODE=real`) |
| `AGORA_REST_KEY`, `AGORA_REST_SECRET` | - | Agora RESTful API credentials (required in real mode) |
| `MOCHI_TURN_KEY` | - | Shared key Agora sends to the turn endpoint (required; `dev-turn-key` in fake mode) |
| `MOCHI_PUBLIC_URL` | `http://localhost:8000` | Public HTTPS address Agora calls |
| `MOCHI_AGORA_MODE` | `real` | `fake` runs without Agora |
| `MOCHI_SILENCE_STRATEGY` | `empty_reply` | or `mute_speaker` (fallback, AGENTS 12.1) |
| `MOCHI_ENABLE_DEV_ROUTES` | `false` | enables `POST /dev/sessions/demo/turn` |
| `MODEL_API_KEY` | - | language-model key (optional) |
| `MOCHI_MODEL_BASE_URL`, `MOCHI_MODEL_NAME` | OpenAI, `gpt-4o-mini` | OpenAI-compatible model |
| `MOCHI_CHANNEL`, `MOCHI_PI_UID`, `MOCHI_AGENT_UID`, `MOCHI_TOKEN_TTL_SECONDS` | `mochi-demo`, 1001, 1002, 3600 | RTC channel, uids, token life |
| `MOCHI_ASR_VENDOR`, `MOCHI_ASR_LANGUAGE`, `MOCHI_ASR_CREDENTIAL_MODE`, `MOCHI_ASR_PARAMS` | ares, `en-US`, empty, `{}` | speech-to-text (`.env.example` uses Agora-managed deepgram) |
| `MOCHI_TTS_VENDOR`, `MOCHI_TTS_CREDENTIAL_MODE`, `MOCHI_TTS_PARAMS` | minimax, empty, `{}` | text-to-speech (`.env.example` uses Agora-managed minimax) |
| `MOCHI_END_OF_SPEECH_SILENCE_MS` | 900 | pause that ends a turn (VAD) |
| `MOCHI_AGENT_IDLE_TIMEOUT_SECONDS` | 60 | Agora `idle_timeout`: the agent exits this long after the Pi leaves (0 = never; hard cap 72 h) |
| `MOCHI_HINT_TTL_SECONDS`, `MOCHI_DECIDE_TIMEOUT_SECONDS` | 8, 2 | hint lifetime; `decide()` time limit |
| `MOCHI_SPEAK_BASE_SECONDS`, `MOCHI_SPEAK_SECONDS_PER_WORD` | 0.6, 0.45 | speaking window for `mute_speaker` |
| `MOCHI_CORS_ORIGINS`, `MOCHI_LOG_LEVEL`, `PORT` | `*`, `INFO`, 8000 | server |

## Docker

```bash
docker build -f services/backend/Dockerfile --build-arg GIT_SHA=$(git rev-parse --short HEAD) -t mochi-backend .
docker run --rm -p 8000:8000 -e MOCHI_AGORA_MODE=fake -e MOCHI_ENABLE_DEV_ROUTES=true mochi-backend
```

`scripts/deploy.sh` does the build, runs the container with `.env`, and checks `/readyz`. The build context
is the repo root. The image runs **one worker** (all state is in memory).

## Render

`render.yaml` is a Blueprint: Render dashboard > New > Blueprint > pick this repo, fill the secrets
(`sync: false`), then set `MOCHI_PUBLIC_URL` to the service URL. It uses a paid `starter` plan on purpose:
a free web service spins down after 15 minutes of silence and takes about a minute to wake, which would
break a live demo. `numInstances: 1`. WebSockets work behind Render's proxy with a single instance.

## Demo-day checklist

1. `.env` filled; backend reachable (Render URL, or `scripts/tunnel.sh` and the printed URL in `MOCHI_PUBLIC_URL`).
2. `MOCHI_ENABLE_DEV_ROUTES=true` for the run (smoke needs it); then `scripts/smoke.sh` against that URL.
3. Open `/readyz`: `ready: true`, `agora_mode: real`, `public_url_set: true`. In real mode the backend refuses to
   start unless `MOCHI_PUBLIC_URL` starts with `https://`.
4. Pi bridge up (`GET /api/devices/home_pi_01/state` polled); Home view on Mochi, Mobile views on both phones,
   Audience view on the projector.
5. `scripts/reset-demo.sh`, then Start on the phone.
6. Leave two ordinary turns between the two demo sentences: a hint silences the next two turns (AGENTS 7.2).

## Known unknowns (AGENTS section 12)

| # | Unknown | Status | Manual test on real hardware |
|---|---|---|---|
| 1 | Empty reply keeps the agent silent | **Unverified.** Not in Agora's docs. Fallback built: `MOCHI_SILENCE_STRATEGY=mute_speaker` | Start; say an ordinary sentence; Mochi must make no sound. If it does, switch the strategy |
| 2 | `adiar` / `guarda-chuva` survive speech-to-text | **Unverified.** `asr.language` is one tag; no documented code-switching | Say both demo sentences; read the `turn` log lines for the transcribed text |
| 3 | Audio both ways on the Pi without hearing itself | **Unverified** (Matheus) | Say `Oi Mochi, what's the word for fila?`; Mochi answers; confirm the answer is not logged as a new `turn` |
| 4 | Tap anywhere registers in the kiosk browser | **Unverified** (Tasnim/Matheus) | Start a round; tap 20 times; each tap must register |

Also open: whether Agora accepts the `006` tokens this builder produces, and which uid the agent token must be
built for. Details in `VERIFIED.md`.

## Layout, rules, tests

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/DECISIONS.md`](docs/DECISIONS.md),
[`docs/PROVENANCE.md`](docs/PROVENANCE.md) and [`services/backend/AGENTS.md`](services/backend/AGENTS.md).
`make verify` runs format check, lint, mypy strict, architecture rules, pytest and the schema check.
