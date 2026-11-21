#!/usr/bin/env bash
# End one latency-test arm: stop the TEST session and print its Agora agent id. See docs/MATHEUS_LATENCY_TEST.md.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/finish-arm.sh <https-test-url> <backend-log-file>
Stops the session on YOUR test backend (POST <url>/api/sessions/demo/stop), then prints the last
agent_started id from the log. Agora's turns are readable only after the agent left, so run this
before scripts/latency-compare.sh. Refuses onrender.com (production)." "${1:-}"
URL="${1:-}"
LOG="${2:-}"
if [ -z "$URL" ] || [ -z "$LOG" ] || [ ! -f "$LOG" ]; then
  echo "Usage: scripts/finish-arm.sh <https-test-url> <backend-log-file>" >&2
  exit 2
fi
case "$URL" in
  *onrender.com*) echo "refusing a Render URL: that is production" >&2; exit 2 ;;
  https://*) ;;
  *) echo "the test URL must be https://: got '$URL'" >&2; exit 2 ;;
esac
curl -fsS -X POST "${URL%/}/api/sessions/demo/stop" >/dev/null || echo "stop call failed (maybe already stopped)" >&2
sleep 3
ID="$(grep "agent_started" "$LOG" | tail -1 | sed -E 's/.*"agent_id": ?"([^"]+)".*/\1/')"
if [ -z "$ID" ]; then
  echo "no agent_started line in $LOG: did a session start?" >&2
  exit 1
fi
echo "agent_id=$ID"
