#!/usr/bin/env bash
# Run a LOCAL backend for one latency-test arm, isolated from production. See docs/LATENCY_TEST_PLAN.md.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/start-test-backend.sh <preset> <https-tunnel-url>
  1. In another terminal: scripts/tunnel.sh   (copy its https://... URL)
  2. scripts/start-test-backend.sh likely https://xxxx.trycloudflare.com
Loads .env (secrets), config/presets/prod.env, then the preset, then FORCES, so no preset can undo it:
  MOCHI_AGORA_MODE=real, MOCHI_CHANNEL=\${MOCHI_TEST_CHANNEL:-mochi-test}, DATABASE_URL and
  MOCHI_LOCAL_DATA empty (memory only: real mode refuses the local file), dev routes on,
  a fresh random MOCHI_TURN_KEY each run, MOCHI_DEVICE_KEY from \$MOCHI_TEST_DEVICE_KEY or the
  git-ignored file .local/test-device-key (created 0600 on first run; give it to the Pi).
The log is kept in .local/latency/<preset>-<time>.log (agent_started and model_usage lines)." "${1:-}"
need uv "install from https://docs.astral.sh/uv/"
PRESET="${1:-}"
TEST_URL="${2:-${MOCHI_TEST_PUBLIC_URL:-}}"
if [ -z "$PRESET" ] || [ -z "$TEST_URL" ]; then
  echo "Usage: scripts/start-test-backend.sh <preset> <https-tunnel-url>   (-h for details)" >&2
  exit 2
fi
case "$TEST_URL" in
  https://*) ;;
  *) echo "the test URL must be https:// (Agora's cloud calls it): got '$TEST_URL'" >&2; exit 2 ;;
esac
case "$TEST_URL" in
  *onrender.com*) echo "refusing a Render URL ('$TEST_URL'): that is production; use scripts/tunnel.sh" >&2; exit 2 ;;
esac
load_preset "$PRESET"

TEST_CHANNEL="${MOCHI_TEST_CHANNEL:-mochi-test}"
if [ "$TEST_CHANNEL" = "mochi-demo" ]; then
  echo "refusing channel mochi-demo: production's channel; pick another MOCHI_TEST_CHANNEL" >&2
  exit 2
fi
DEVICE_KEY_FILE="$ROOT/.local/test-device-key"
if [ -z "${MOCHI_TEST_DEVICE_KEY:-}" ] && [ ! -s "$DEVICE_KEY_FILE" ]; then
  mkdir -p "$ROOT/.local"
  (umask 077 && random_key > "$DEVICE_KEY_FILE")
  echo "new device key written to $DEVICE_KEY_FILE (copy it to the Pi's .env as MOCHI_DEVICE_KEY)" >&2
fi

# Isolation, applied last on purpose.
export MOCHI_AGORA_MODE=real
export MOCHI_CHANNEL="$TEST_CHANNEL"
export MOCHI_PUBLIC_URL="$TEST_URL"
export DATABASE_URL=""
export MOCHI_LOCAL_DATA=""
export MOCHI_ENABLE_DEV_ROUTES=true
MOCHI_TURN_KEY="$(random_key)"
export MOCHI_TURN_KEY
MOCHI_DEVICE_KEY="${MOCHI_TEST_DEVICE_KEY:-$(cat "$DEVICE_KEY_FILE")}"
export MOCHI_DEVICE_KEY

LOG_DIR="$ROOT/.local/latency"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/$PRESET-$(date -u +%Y%m%dT%H%M%SZ).log"
echo "preset=$PRESET channel=$MOCHI_CHANNEL url=$MOCHI_PUBLIC_URL storage=memory log=$LOG" >&2
echo "Pi: config/mochi.local.toml [backend] kind=\"mochi_backend\", mochi_backend_url=\"$MOCHI_PUBLIC_URL\"" >&2
cd "$ROOT/services/backend"
# No --reload: a reload would wipe the in-memory session in the middle of a run.
uv run uvicorn mochi_backend.app:app_from_env --factory --port "${PORT:-8000}" 2>&1 | tee -a "$LOG"
