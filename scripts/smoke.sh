#!/usr/bin/env bash
# Pre-demo check against a running server. Prints PASS/FAIL per step; exits 1 if any failed.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/smoke.sh
Needs the dev routes (MOCHI_ENABLE_DEV_ROUTES=true) and jq. Leaves the session stopped and reset.
Two filler turns sit between the demo sentences because a hint silences the next two turns (AGENTS 7.2)." "${1:-}"
need jq "install jq"

FAILED=0
check() { # check NAME ACTUAL EXPECTED
  if [ "$2" = "$3" ]; then echo "PASS  $1"; else echo "FAIL  $1 (got '$2', expected '$3')"; FAILED=1; fi
}
turn() { post /dev/sessions/demo/turn "$(jq -nc --arg t "$1" '{text:$t}')"; }

check "readyz" "$(curl -sf "$BASE_URL/readyz" | jq -r .ready)" "true"
post /api/demo/reset >/dev/null
check "start" "$(post /api/sessions/demo/start | jq -r .capturing)" "true"
check "hint 1: postpone" "$(turn 'I need to adiar my meeting tomorrow.' | jq -r .decision.hint.expression)" "postpone"
turn 'That sounds stressful.' >/dev/null
check "ordinary talk stays quiet" "$(turn 'Yes, I will postpone it until Thursday.' | jq -r .decision.decision)" "IGNORE"
check "hint 2: umbrella" "$(turn 'I forgot my guarda-chuva at the office.' | jq -r .decision.hint.expression)" "umbrella"
check "round starts" "$(post /api/sessions/demo/activity/start | jq -r .state)" "ACTIVE_ROUND"
check "round result" "$(post /api/sessions/demo/activity/result '{"result":"guessed"}' | jq -r .revealed_word)" "umbrella"
check "stop" "$(post /api/sessions/demo/stop | jq -r .capturing)" "false"
check "device idle after stop" "$(curl -sf "$BASE_URL/api/devices/home_pi_01/state" | jq -c '[.capturing,.agora]')" "[false,null]"
post /api/demo/reset >/dev/null
check "reset" "$(curl -sf "$BASE_URL/readyz" | jq -r .ready)" "true"
exit "$FAILED"
