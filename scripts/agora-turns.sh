#!/usr/bin/env bash
# Print Agora's per-turn latency table for an agent. Read-only call to Agora's Turns API.
# Usage: scripts/agora-turns.sh [AGENT_ID]   (or pipe the backend log: render logs | scripts/agora-turns.sh)
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/agora-turns.sh [AGENT_ID]
AGENT_ID is logged by the backend as the agent_started line when a session starts.
Needs AGORA_APP_ID, AGORA_REST_KEY, AGORA_REST_SECRET in the environment or ./.env." "${1:-}"
need uv "install uv"
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
cd "$ROOT/services/backend"
PYTHONPATH="$ROOT/services/backend" uv run python "$ROOT/scripts/agora_turns.py" "$@"
