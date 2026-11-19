#!/usr/bin/env bash
# Run the fixtures against the REAL model and print a pass rate. Uses the network; not part of make verify.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/eval-intelligence.sh
Needs MODEL_API_KEY (and optionally MOCHI_MODEL_BASE_URL, MOCHI_MODEL_NAME) in the environment or ./.env.
Fixtures that need the model (cases 5-9 beyond the lexicon) are judged by the real model." "${1:-}"
need uv "install uv"
if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
cd "$ROOT/services/backend"
PYTHONPATH="$ROOT/services/backend" uv run python "$ROOT/scripts/eval_intelligence.py"
