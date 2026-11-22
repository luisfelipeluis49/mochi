# Provenance

The hackathon (Nov 21-22, 2026) requires a record of what existed before it started. **Everything below was
created on 2026-11-19, before the event.** Rule: **append a row for every new component** (hackathon rules,
section 5.5) and mark it `pre-existing` or `during hackathon`.

| Component | Owner | Date | Status | Notes |
|---|---|---|---|---|
| Repository scaffold, tooling, Makefile, CI workflow | Luís (built by a coding agent) | 2026-11-19 | pre-existing | ruff, mypy strict, pytest, architecture-rules test |
| `packages/contracts` (Pydantic models, examples, JSON Schema) | Matheus's area, built here by request | 2026-11-19 | pre-existing | mirrors AGENTS 6 (v0.4); two provisional models |
| `packages/fixtures/decisions.json` | Kauê's area, built here by request | 2026-11-19 | pre-existing | 72 sentences |
| `services/backend/.../intelligence/` | Kauê's area, built here by request | 2026-11-19 | pre-existing | rules, lexicon, model port, memory (the game's rounds were removed on 2026-11-21, D-43) |
| `services/backend/.../gateway/` | Luís | 2026-11-19 | pre-existing | turn pipeline, hub, session/device, Agora adapter (the activity service was removed with the game, D-43) |
| `services/backend/.../platform/`, `settings.py`, `composition.py`, `app.py` | Luís | 2026-11-19 | pre-existing | |
| `scripts/` | Luís | 2026-11-19 | pre-existing | start-dev, say, reset-demo, smoke, tunnel, deploy, eval, watch_ws |
| `services/backend/Dockerfile`, `.dockerignore`, `render.yaml` | Luís | 2026-11-19 | pre-existing | |
| `AGENTS.md`, `.claude/agents/*` | team / Luís | 2026-11-19 | pre-existing | team context; three read-only subagent definitions |
| Third-party: FastAPI, uvicorn, httpx, pydantic, pydantic-settings, agora-token-builder | upstream | - | third-party | versions in `services/backend/uv.lock` |
| `apps/web` (Home, Mobile, Audience views) | Tasnim | 2026-11-21 | during hackathon | React + TypeScript (Vite); merged on top of the backend |
| `apps/glasses` (Mochi AR, Rokid Fluency Helper) | Suhuai | 2026-11-21 | during hackathon | out of the hackathon MVP (AGENTS section 1); proposed `surface=ar` in AGENTS 6.6 |
| `hardware/pi-bridge` | Matheus (commits by Suhuai's account) | 2026-11-20 | **to confirm with the owners** | Agora IoT SDK audio bridge and device scripts; first commit 2026-11-20, merged in PR #1; the status (`pre-existing` or `during hackathon`) is the owners' to state |
| `hardware/pi-bridge/sounds/*.wav` (six sentences Mochi says without a connection) | Suhuai, generated | 2026-11-21 | during hackathon | synthesised with Piper voices: English `en_US-libritts_r-medium` speaker 250 (dataset LibriTTS-R, CC BY 4.0), Portuguese `pt_BR-faber-medium` (CC0); texts in `hardware/pi-bridge/README.md` |
| `scripts/test-client/`, `scripts/test-client.sh`, `docs/REAL_TURN_RUNBOOK.md` | Luis, built here | 2026-11-20 | pre-existing | real-turn test client and runbook |
| Papear: `services/backend/.../team/`, the company tables and routes, review mode, `docs/TEAM_VIEW.md` | built on Suhuai's account, owners to be agreed (DECISIONS D-43 to D-45) | 2026-11-21 | during hackathon | the product change of 2026-11-21: two session modes, the game removed, session records, word moments and the team view |
