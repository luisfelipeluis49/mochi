# Build log

Append one entry per checkpoint: what works and how to see it.

## Scaffold
- Repo, tooling, platform wrappers, architecture-rules test. See it: `make -C services/backend verify`.

## Contracts
- Pydantic models for AGENTS section 6, one JSON example per event/payload, exported JSON Schema.
  See it: `make -C services/backend test`, `make -C services/backend contracts-schema`.

## Intelligence (M0-M4 intelligence rows)
- `decide()` cases 1-9, quiet rules, whose-word rule, learning states, `handle()` rounds, memory.
  See it: `make -C services/backend test`; 66 sentences in `packages/fixtures/decisions.json`.

## Gateway (M0-M4 gateway rows)
- Turn endpoint (shared key, SSE), `/dev` turn, hub with per-connection routing and leak guard, live hint
  expiry/replacement, session start/stop, device state, activity endpoints, reset, silence strategies,
  Agora REST adapter + token issuer behind ports, `MOCHI_AGORA_MODE=fake`.
  See it: `make -C services/backend test` (integration walkthrough: `tests/integration/test_gateway_flow.py`).

## Scripts, Docker, Render, CI
- `scripts/smoke.sh` against a live server: all steps PASS. Container built and run (non-root, healthy,
  `/healthz` returns the git SHA). `render.yaml`, `.github/workflows/verify.yml` written (not pushed).

## Review fixes
- Smoke and the walkthrough now assert a plain sentence produces IGNORE and publishes nothing (outside any cooldown).
- Real mode requires an https `MOCHI_PUBLIC_URL`; `/readyz` no longer reads ready for localhost in real mode.
- Stale-schema check is also a pytest; rule exceptions inventoried in DECISIONS D-17.
