#!/usr/bin/env bash
# Start the backend (fake Agora, dev routes on, reload) and the web app if apps/web has a dev script.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/start-dev.sh
Loads ./.env if present, then runs the backend on :\${PORT:-8000} with MOCHI_AGORA_MODE=fake.
Override with MOCHI_AGORA_MODE=real in .env to talk to Agora." "${1:-}"
need uv "install from https://docs.astral.sh/uv/"

if [ -f "$ROOT/.env" ]; then set -a; . "$ROOT/.env"; set +a; fi
export MOCHI_AGORA_MODE="${MOCHI_AGORA_MODE:-fake}"
export MOCHI_ENABLE_DEV_ROUTES="${MOCHI_ENABLE_DEV_ROUTES:-true}"
if [ "$MOCHI_AGORA_MODE" = "fake" ] && [ -z "${DATABASE_URL:-}" ]; then  # saved words and voices survive a restart
  export MOCHI_LOCAL_DATA="${MOCHI_LOCAL_DATA:-$ROOT/.local/mochi-data.json}"
fi

WEB_PID=""
if [ -f "$ROOT/apps/web/package.json" ] && grep -q '"dev"' "$ROOT/apps/web/package.json"; then
  (cd "$ROOT/apps/web" && npm run dev) & WEB_PID=$!
  trap 'kill "$WEB_PID" 2>/dev/null || true' EXIT
fi
cd "$ROOT/services/backend"
uv run uvicorn mochi_backend.app:app_from_env --factory --reload --port "${PORT:-8000}"
