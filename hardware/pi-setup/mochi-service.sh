#!/usr/bin/env bash
# Keep Mochi running: start it at boot and restart it if it stops (or remove that with --remove).
# Mochi then listens offline all the time; an Agora session exists only between a wake phrase and a
# goodbye phrase / silence timeout (hardware/pi-bridge/config/mochi.toml).
#   systemctl --user status mochi        is it running?
#   journalctl --user-unit mochi -f        live log
#   systemctl --user restart mochi       after editing config/mochi.toml or .env
set -euo pipefail
BRIDGE="$(cd "$(dirname "$0")/../pi-bridge" && pwd)"
UNIT="$HOME/.config/systemd/user/mochi.service"
if [ "${1:-}" = "--remove" ]; then
  systemctl --user disable --now mochi.service 2>/dev/null || true
  rm -f "$UNIT"; systemctl --user daemon-reload
  echo "Mochi no longer starts by itself."; exit 0
fi
mkdir -p "$(dirname "$UNIT")"
cat > "$UNIT" <<UNIT
[Unit]
Description=Mochi: offline wake phrase, then an Agora session
After=emeet-volume.service sound.target

[Service]
WorkingDirectory=$BRIDGE
ExecStart=$BRIDGE/scripts/mochi.sh
Restart=always
RestartSec=3
# Ctrl-C equivalent: the supervisor ends any live session before leaving
KillSignal=SIGINT
TimeoutStopSec=20

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable mochi.service
systemctl --user restart mochi.service
loginctl show-user "$USER" -p Linger | grep -q yes || echo "Note: run 'loginctl enable-linger $USER' so Mochi also starts before anyone logs in."
echo "Mochi is running and will start at boot. Log: journalctl --user-unit mochi -f   Undo: $0 --remove"
