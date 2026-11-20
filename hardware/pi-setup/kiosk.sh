#!/usr/bin/env bash
# Open the Home view full screen on Mochi's 3.5" display (480x320, labwc/Wayland).
#
#   ./kiosk.sh                       # opens $MOCHI_HOME_URL, or Mochi's face (face.html)
#   ./kiosk.sh "file://$PWD/placeholder.html"   # the touch test page
#   ./kiosk.sh off                   # a black page: the screen as dark as it gets (its backlight has no switch)
#   ./kiosk.sh http://host:5173/home?device=home_pi_01
#
# Works from SSH too: it attaches to the desktop session on the Pi's screen.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
URL="${1:-${MOCHI_HOME_URL:-file://$HERE/face.html}}"
[ "$URL" = off ] && URL='data:text/html,<body style="background:%23000;cursor:none">'

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
if [ ! -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]; then
  echo "No Wayland session at $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY (is the desktop running on the screen?)" >&2
  exit 1
fi

# Screen blanking off: Raspberry Pi OS blanks the screen through swayidle.
pkill -x swayidle 2>/dev/null || true

# One kiosk at a time.
pkill -f -- "--user-data-dir=$HOME/.cache/mochi-kiosk" 2>/dev/null || true
sleep 0.5

echo "Opening $URL"
exec chromium \
  --ozone-platform=wayland \
  --kiosk "$URL" \
  --user-data-dir="$HOME/.cache/mochi-kiosk" \
  --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --disable-features=Translate,TouchpadOverscrollHistoryNavigation \
  --overscroll-history-navigation=0 --disable-pinch \
  --touch-events=enabled \
  --password-store=basic \
  --autoplay-policy=no-user-gesture-required \
  >/tmp/mochi-kiosk.log 2>&1
