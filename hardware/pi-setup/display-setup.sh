#!/usr/bin/env bash
# Set up Mochi's 3.5" SPI screen for the way the device is mounted, now and after every boot.
#   ./display-setup.sh           upside down (the shell holds the Pi inverted), smooth animation
#   ./display-setup.sh normal    the panel's own orientation (also accepts 90, 180, 270)
#
# For a dark screen use "./kiosk.sh off" (a black page). Do NOT switch the output itself off with
# wlr-randr: it is the only output, and switching it back on crashed labwc and ended the desktop
# session (2026-11-20).
#
# Two things are set:
# - Rotation. The touch panel is mapped to the output in ~/.config/labwc/rc.xml, so labwc turns
#   touch coordinates with it.
# - Refresh rate. The panel's driver reports its only mode as 0.007 Hz, and Chromium then draws
#   about one frame per second. A custom mode of the same size at 30 Hz makes it draw normally.
set -euo pipefail
TRANSFORM="${1:-180}"
case "$TRANSFORM" in normal|90|180|270) ;; *) echo "use: $0 [normal|90|180|270]" >&2; exit 2 ;; esac
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
# the real screen: not the NOOP placeholder the compositor adds while the screen is off
OUTPUT="${MOCHI_OUTPUT:-$(wlr-randr | awk '/^[^ ]/ && $1 !~ /^NOOP/ {print $1; exit}')}"
SIZE="$(wlr-randr | awk -v out="$OUTPUT" '/^[^ ]/ {cur = $1} cur == out && / px, / {print $1; exit}')"
wlr-randr --output "$OUTPUT" --custom-mode "$SIZE@30Hz" --transform "$TRANSFORM"
# kanshi applies this file when the desktop starts (Raspberry Pi OS's Screen Configuration tool
# writes the same file).
mkdir -p "$HOME/.config/kanshi"
cat > "$HOME/.config/kanshi/config" <<KANSHI
profile {
	output $OUTPUT enable mode --custom $SIZE@30Hz transform $TRANSFORM
}
KANSHI
pkill -HUP -x kanshi 2>/dev/null || true
sleep 1
wlr-randr | awk -v out="$OUTPUT" '/^[^ ]/ {cur = $1} cur == out && /current/ {mode = $1 " " $3 " " $4} cur == out && /Transform:/ {t = $2}
  END {print out ": " mode ", transform " t "  (saved in ~/.config/kanshi/config)"}'
