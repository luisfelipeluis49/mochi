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
check "ordinary talk: no hint" "$(turn 'Did you watch the match yesterday?' | jq -c '[.decision.decision,.decision.hint]')" '["IGNORE",null]'
check "hint 1: postpone" "$(turn 'I need to adiar my meeting tomorrow.' | jq -r .decision.hint.expression)" "postpone"
turn 'That sounds stressful.' >/dev/null
check "turn right after a hint stays quiet" "$(turn 'Yes, I will postpone it until Thursday.' | jq -r .decision.decision)" "IGNORE"
check "hint 2: umbrella" "$(turn 'I forgot my guarda-chuva at the office.' | jq -r .decision.hint.expression)" "umbrella"
check "stop" "$(post /api/sessions/demo/stop | jq -r .capturing)" "false"
# A review is one person's own session (a phone's), so it runs under its own id.
check "review starts for Ana" "$(post /api/sessions/smoke-review/start '{"mode":"review","user_id":"ana"}' | jq -c '[.mode,.participants]')" '["review",["ana"]]'
post /dev/sessions/smoke-review/turn '{"text":"I left my umbrella at the office."}' >/dev/null
check "review stops" "$(post /api/sessions/smoke-review/stop | jq -r .capturing)" "false"
check "team view: a meeting, a review, a recalled word" "$(curl -sf "$BASE_URL/api/companies/demo/insights?viewer=ana" | jq -c '[.totals.meetings,.totals.reviews,.funnel.reinforced]')" "[1,1,1]"
check "team view is for administrators" "$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/api/companies/demo/insights?viewer=ben")" "403"
check "device idle after stop" "$(curl -sf "$BASE_URL/api/devices/home_pi_01/state" | jq -c '[.capturing,.agora]')" "[false,null]"
post /api/demo/reset >/dev/null
check "reset" "$(curl -sf "$BASE_URL/readyz" | jq -r .ready)" "true"
exit "$FAILED"
