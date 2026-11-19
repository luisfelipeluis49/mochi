#!/usr/bin/env bash
# Clear saved words, the game and the live hint. Capturing is left as it is.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/reset-demo.sh
Posts to \$MOCHI_BASE_URL/api/demo/reset." "${1:-}"
post /api/demo/reset | python3 -m json.tool
