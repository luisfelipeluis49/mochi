#!/usr/bin/env bash
# Compare Agora's per-turn latency between test arms (p50/p95 per stage). Read-only call to Agora.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/latency-compare.sh LABEL=AGENT_ID [LABEL=AGENT_ID ...]
The first arm is the baseline the others are compared to, e.g.
  scripts/latency-compare.sh PROD=A46AF... SAFE=B12CD... LIKELY=C34EF...
AGENT_ID is the agent_started line of the arm's log (.local/latency/<preset>-*.log); a saved Turns API
reply (a .json file) works too. Turns are readable only after the agent left: press Stop first.
Needs AGORA_APP_ID, AGORA_REST_KEY, AGORA_REST_SECRET in the environment or ./.env." "${1:-}"
need uv "install uv"
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
ARGS=()
for spec in "$@"; do  # a relative .json path must survive the cd below
  label="${spec%%=*}"; source="${spec#*=}"
  if [ "$label" != "$spec" ] && [ -f "$source" ]; then spec="$label=$(cd "$(dirname "$source")" && pwd)/$(basename "$source")"; fi
  ARGS+=("$spec")
done
cd "$ROOT/services/backend"
PYTHONPATH="$ROOT/services/backend" uv run python "$ROOT/scripts/latency_compare.py" "${ARGS[@]}"
