#!/usr/bin/env bash
# Expose localhost:8000 on a public HTTPS URL so Agora's cloud can call the backend.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/tunnel.sh
Uses cloudflared, falling back to ngrok. Prints the MOCHI_PUBLIC_URL line to put in .env.
Neither tool is installed by this script." "${1:-}"
PORT_TO_EXPOSE="${PORT:-8000}"

if command -v cloudflared >/dev/null 2>&1; then
  echo "Starting cloudflared; copy the https://...trycloudflare.com URL below into MOCHI_PUBLIC_URL=" >&2
  exec cloudflared tunnel --url "http://localhost:$PORT_TO_EXPOSE"
elif command -v ngrok >/dev/null 2>&1; then
  echo "Starting ngrok; copy the https URL below into MOCHI_PUBLIC_URL=" >&2
  exec ngrok http "$PORT_TO_EXPOSE"
fi
echo "Neither cloudflared nor ngrok is installed." >&2
echo "Install one: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ or https://ngrok.com/download" >&2
exit 1
