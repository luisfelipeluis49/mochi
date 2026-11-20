#!/usr/bin/env bash
# Run the bridge, loading settings from hardware/pi-bridge/.env if it exists.
set -euo pipefail
cd "$(dirname "$0")/.."
for f in .env .env.session; do [ -f "$f" ] && { set -a; . "./$f"; set +a; }; done
make -s
exec ./build/mochi-bridge "$@"
