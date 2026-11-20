# Provenance

The hackathon (Nov 21-22, 2026) requires a record of what existed before it started. **Everything below was
created on 2026-11-19, before the event.** Rule: **append a row for every new component** (hackathon rules,
section 5.5) and mark it `pre-existing` or `during hackathon`.

| Component | Owner | Date | Status | Notes |
|---|---|---|---|---|
| Repository scaffold, tooling, Makefile, CI workflow | Luís (built by a coding agent) | 2026-11-19 | pre-existing | ruff, mypy strict, pytest, architecture-rules test |
| `packages/contracts` (Pydantic models, examples, JSON Schema) | Matheus's area, built here by request | 2026-11-19 | pre-existing | mirrors AGENTS 6 (v0.4); two provisional models |
| `packages/fixtures/decisions.json` | Kauê's area, built here by request | 2026-11-19 | pre-existing | 72 sentences |
| `services/backend/.../intelligence/` | Kauê's area, built here by request | 2026-11-19 | pre-existing | rules, lexicon, model port, rounds, memory |
| `services/backend/.../gateway/` | Luís | 2026-11-19 | pre-existing | turn pipeline, hub, session/device/activity, Agora adapter |
| `services/backend/.../platform/`, `settings.py`, `composition.py`, `app.py` | Luís | 2026-11-19 | pre-existing | |
| `scripts/` | Luís | 2026-11-19 | pre-existing | start-dev, say, reset-demo, smoke, tunnel, deploy, eval, watch_ws |
| `services/backend/Dockerfile`, `.dockerignore`, `render.yaml` | Luís | 2026-11-19 | pre-existing | |
| `AGENTS.md`, `.claude/agents/*` | team / Luís | 2026-11-19 | pre-existing | team context; three read-only subagent definitions |
| Third-party: FastAPI, uvicorn, httpx, pydantic, pydantic-settings, agora-token-builder | upstream | - | third-party | versions in `services/backend/uv.lock` |
| `apps/web`, `hardware/` | Tasnim, Matheus | - | not started here | only README pointers exist |
