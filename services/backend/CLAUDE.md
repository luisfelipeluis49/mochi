@AGENTS.md
@../../AGENTS.md

## Quick reference
- `make install` / `make verify` / `make test` / `make run` (fake Agora: `MOCHI_AGORA_MODE=fake`).
- Check Agora details through the Agora MCP and update `src/mochi_backend/gateway/agora/VERIFIED.md`.
- Only the hub publishes events and sets every envelope field.
- Never log secrets (keys, tokens, certificates).
- When the real path breaks, find the last step that left a trace: bridge log, the backend log line
  for the turn, the decision line, the published-event line, then `?debug=1` and the screen.
