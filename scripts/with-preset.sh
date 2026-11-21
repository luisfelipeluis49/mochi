#!/usr/bin/env bash
# Run one command with a latency-test preset loaded (.env, then prod.env, then the preset).
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/with-preset.sh <preset> -- <command> [args...]
Presets: config/presets/*.env (prod, safe, ares, cartesia, stream, likely, stretch).
Only loads settings: it does NOT isolate from production. To run a test backend use
scripts/start-test-backend.sh, which forces its own channel, keys and memory storage." "${1:-}"
PRESET="${1:-}"
shift || true
[ "${1:-}" = "--" ] && shift
if [ -z "$PRESET" ] || [ "$#" -eq 0 ]; then
  echo "Usage: scripts/with-preset.sh <preset> -- <command> [args...]" >&2
  exit 2
fi
load_preset "$PRESET"
exec "$@"
