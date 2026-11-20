#!/usr/bin/env bash
# Serve the browser test client on http://localhost:5173 (the Agora Web SDK needs https or localhost).
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/test-client.sh
Serves scripts/test-client/ on http://localhost:5173. The page joins the Agora channel as the Pi,
using GET /api/devices/home_pi_01/state of the backend named in the page (the Render URL). Wear headphones.
Loads the Agora Web SDK from download.agora.io (a CDN script, not an npm dependency)." "${1:-}"
need python3 "install Python 3"
echo "Test client: http://localhost:5173  (Ctrl+C to stop)"
exec python3 -m http.server 5173 --bind 127.0.0.1 --directory "$ROOT/scripts/test-client"
