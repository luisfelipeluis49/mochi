#!/usr/bin/env bash
# Check the wake / goodbye phrases without Agora: prints what the Pi hears and when a phrase matches.
#   scripts/wake-test.sh              listen on the M1A
#   scripts/wake-test.sh --quiet      print matches only
#   scripts/wake-test.sh --chime      also beep on a match (rising = wake, falling = goodbye)
#   scripts/wake-test.sh --wav x.wav  read a 16 kHz mono recording instead
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f third_party/wake/zipa-small/model.int8.onnx ] || ./scripts/fetch-wake-model.sh
exec .venv/bin/python -u -m mochi_device.wakeword "$@"
