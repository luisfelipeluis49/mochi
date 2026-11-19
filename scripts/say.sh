#!/usr/bin/env bash
# Send a typed sentence to the backend as if Agora had heard it.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/say.sh \"<sentence>\"
Posts to \$MOCHI_BASE_URL (default http://localhost:8000)/dev/sessions/demo/turn and pretty-prints
the reply and decision. The session must be started (POST /api/sessions/demo/start)." "${1:-}"
[ $# -eq 1 ] || { echo "usage: scripts/say.sh \"<sentence>\"" >&2; exit 2; }
need python3 "needed to encode the sentence as JSON"

body="$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$1")"
post /dev/sessions/demo/turn "$body" | python3 -m json.tool
