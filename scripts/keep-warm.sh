#!/usr/bin/env bash
# Ping the backend's /healthz so Render's free plan does not put it to sleep (it does after 15 idle minutes).
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/keep-warm.sh [--once] [URL]
URL defaults to \$MOCHI_PUBLIC_URL (environment or ./.env). Pings URL/healthz every
\${KEEP_WARM_SECONDS:-240} seconds until Ctrl-C; --once pings one time and exits with curl's status.
Sends no keys." "${1:-}"
need curl "install curl"
ONCE=false
if [ "${1:-}" = "--once" ]; then ONCE=true; shift; fi
if [ -z "${1:-}" ] && [ -z "${MOCHI_PUBLIC_URL:-}" ] && [ -f "$ROOT/.env" ]; then
  MOCHI_PUBLIC_URL="$(set -a; . "$ROOT/.env"; printf '%s' "${MOCHI_PUBLIC_URL:-}")"
fi
TARGET="${1:-${MOCHI_PUBLIC_URL:-}}"
if [ -z "$TARGET" ]; then
  echo "no URL: pass one or set MOCHI_PUBLIC_URL" >&2
  exit 2
fi
TARGET="${TARGET%/}/healthz"

ping_once() {
  local stamp
  stamp="$(date -u +%H:%M:%S)"
  if curl --silent --show-error --fail --max-time 90 -o /dev/null -w "$stamp %{http_code} %{time_total}s\n" "$TARGET"; then
    return 0
  fi
  echo "$stamp ping failed: $TARGET" >&2
  return 1
}

if [ "$ONCE" = true ]; then ping_once; exit $?; fi
echo "pinging $TARGET every ${KEEP_WARM_SECONDS:-240} s; Ctrl-C to stop" >&2
while true; do
  ping_once || true
  sleep "${KEEP_WARM_SECONDS:-240}"
done
