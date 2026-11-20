#!/usr/bin/env bash
# Run Mochi: offline wake word -> Agora session -> goodbye/timeout -> back to offline.
set -euo pipefail
cd "$(dirname "$0")/.."
make -s
[ -f third_party/wake/zipa-small/model.int8.onnx ] && [ -f third_party/voice/3dspeaker_campplus_zh_en.onnx ] \
  || ./scripts/fetch-wake-model.sh
exec .venv/bin/python -u -m mochi_device.main "$@"
