#!/usr/bin/env bash
# Start the kiosk automatically when the Pi's desktop starts (or remove that with --remove).
# Writes one marked line into ~/.config/labwc/autostart.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FILE="$HOME/.config/labwc/autostart"
MARK="# mochi-kiosk"
mkdir -p "$(dirname "$FILE")"; touch "$FILE"
sed -i "/$MARK/d" "$FILE"
if [ "${1:-}" = "--remove" ]; then
  echo "Removed kiosk from $FILE"; exit 0
fi
echo "/usr/bin/lwrespawn $HERE/kiosk.sh & $MARK" >> "$FILE"
echo "Kiosk will start with the desktop (edit MOCHI_HOME_URL in ~/.config/labwc/environment to change the page)."
echo "Undo with: $0 --remove"
