#!/usr/bin/env bash
# Check the M1A without Agora: record 5 s from its microphone, then play it back.
set -euo pipefail
DEV="${MOCHI_MIC:-plughw:CARD=M1A,DEV=0}"
OUT="$(mktemp --suffix=.wav)"
trap 'rm -f "$OUT"' EXIT
echo "Recording 5 seconds from $DEV... talk now."
arecord -D "$DEV" -f S16_LE -r 16000 -c 1 -d 5 -q "$OUT"
echo "Playing it back through ${MOCHI_SPEAKER:-$DEV}..."
aplay -D "${MOCHI_SPEAKER:-$DEV}" -q "$OUT"
echo "Done. If you heard yourself, the M1A works in both directions."
