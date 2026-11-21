# Latency test presets

One file per test arm. No secrets: keys stay in `./.env` (git-ignored). `prod.env` is today's production
setting. Every other file lists only what its arm changes and is loaded **on top of** `prod.env`.
`likely.env` and `stretch.env` are written out in full, with no nested includes.
`tests/unit/test_presets.py` checks that they still equal the sum of their parts.

Load order: `./.env` (secrets) → `prod.env` → `<arm>.env`. Later files win.

```bash
# any command with a preset's settings (does NOT isolate from production)
scripts/with-preset.sh ares -- env | grep MOCHI_ASR

# by hand, in the current shell
set -a; . ./.env; . config/presets/prod.env; . config/presets/ares.env; set +a

# a test backend for one arm, isolated from production (see docs/LATENCY_TEST_PLAN.md)
scripts/start-test-backend.sh ares https://<tunnel>.trycloudflare.com
```

`MOCHI_CANCEL_STALE_TURNS`, `MOCHI_CHARACTER_HEDGE_SECONDS` and `MOCHI_STREAM_REPLY` are added on this
branch by separate work. A backend without them ignores them (`Settings` has `extra="ignore"`), so the
SAFE and STREAM arms only mean something on a build that has those flags.

## The arms and what each should save

These numbers come from the round-4 estimate (golden session plus code reading). They are
**not measured**. p50 of the time to Mochi's first sound on a spoken reply, today about 2.9-3.2 s
(or 3.6-3.9 s if `asr_ttlw` excludes the end-of-speech wait).

| Preset | Changes | Stage | Saved p50 (low / likely / high) | Confidence |
|---|---|---|---|---|
| `prod` | nothing: the baseline | - | - | - |
| `safe` | drop stale turns, character hedge 1.0 s | llm (queue, tail) | 0 / 0.03 / 0.10 s; p95 -0.4 to -1.0 s | high that p50 barely moves; low for p95 |
| `ares` | ARES `en-US,pt-BR` + 24 keywords instead of gpt-4o-transcribe | asr_ttlw | 0.30 / 0.45 / 0.55 s; also on hints | medium; only if the accuracy go/no-go passes |
| `cartesia` | Cartesia sonic-3.6 (Jacqueline) instead of MiniMax | tts_ttfb | 0.20 / 0.23 / 0.27 s; spoken lines only | medium; only if the listening test passes |
| `stream` | stream free-chat replies | llm | 0.05 / 0.20 / 0.45 s; free chat only | low; unmeasured, estimates conflict |
| `likely` | safe + ares + cartesia | all | 0.55-1.0 s in total | medium; most of it is ARES |
| `stretch` | likely + stream + end of speech 480 ms | all | 0.75-1.75 s, likely 1.2 s | low |

End of speech 600 → 480 ms saves about 0.12 s, but it may cut people off and split "trails off… um"
turns. It is in `stretch` only. Hints on screen gain from ARES, end of speech and stale-turn
dropping, and not from Cartesia or streaming.

## Caveats per preset

- `prod`: the hint model `gpt-5.4-mini` comes from the round-4 facts. `render.yaml` still says
  `gpt-4o-mini`, and the Render dashboard can override it. Check the dashboard before trusting it.
- `ares`: needs `MOCHI_ASR_LEXICON_WORDS=true` to send the 24 probed keywords; production has it false
  (D-36). Naming words can make the recogniser "hear" them in background speech, and the test plan
  checks this. Agora accepted the language pair (HTTP 200). How well it recognises speech is unknown.
- `cartesia`: the language is fixed per session (`en`), so Portuguese lines will sound accented.
  A wrong voice id fails silently. Billing under Agora's managed key is undocumented.
