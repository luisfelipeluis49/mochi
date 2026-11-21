#!/usr/bin/env bash
# Estimate the cost of one test session per arm, and per 10-minute demo. Reads Agora's turns only
# when an agent id is given (read-only); prices come from config/prices.json.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/cost-estimate.sh [--prices FILE] LABEL,ASR,TTS,DURATION[,LOG] ...
  scripts/cost-estimate.sh PROD,openai,minimax,A46AF...,.local/latency/prod-20261121T190000Z.log \\
                           LIKELY,ares,cartesia,6.5,.local/latency/likely-20261121T193000Z.log
DURATION is minutes, an agent id (needs AGORA_APP_ID, AGORA_REST_KEY, AGORA_REST_SECRET) or a saved
Turns API reply (.json). LOG holds the backend's model_usage lines (- reads stdin)." "${1:-}"
need uv "install uv"
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
ARGS=()
for spec in "$@"; do  # relative log and .json paths must survive the cd below
  IFS=, read -r -a parts <<< "$spec"
  for i in "${!parts[@]}"; do
    if { [ "$i" -ge 3 ] || [ "${#parts[@]}" -eq 1 ]; } && [ -f "${parts[$i]}" ]; then
      parts[$i]="$(cd "$(dirname "${parts[$i]}")" && pwd)/$(basename "${parts[$i]}")"
    fi
  done
  ARGS+=("$(IFS=,; printf '%s' "${parts[*]}")")
done
cd "$ROOT/services/backend"
PYTHONPATH="$ROOT/services/backend" uv run python "$ROOT/scripts/cost_estimate.py" "${ARGS[@]}"
