#!/usr/bin/env bash
# Download the models Mochi listens with, into third_party/ (gitignored, ~100 MB):
#   wake/zipa-small   - multilingual phone recogniser (Zhu et al., ACL 2025; Creative Commons, see the model page)
#   wake/silero_vad   - voice activity detector, from the sherpa-onnx releases
#   voice/3dspeaker_campplus_zh_en - speaker embeddings for recognising who is talking (3D-Speaker, Apache-2.0)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p third_party/wake/zipa-small && cd third_party/wake
ZIPA=https://huggingface.co/anyspeech/zipa-small-crctc-ns-no-diacritics-700k/resolve/main
get() {  # get <file> <url> <sha256>
  if [ ! -f "$1" ] || ! echo "$3  $1" | sha256sum -c --status; then
    curl -fL --progress-bar -o "$1" "$2"
    echo "$3  $1" | sha256sum -c --quiet
  fi
}
get zipa-small/model.int8.onnx "$ZIPA/model.int8.onnx" e79c5ec351001b8d1d05c167e5cb294c84dd616dc1733479b05971b953378c9a
get zipa-small/tokens.txt      "$ZIPA/tokens.txt"      f8e042a0c9130532b22d03ec7cae2f75a23fbec70c450c31a8efb51787b2b8fe
get silero_vad.onnx https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx \
  9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6
mkdir -p ../voice
get ../voice/3dspeaker_campplus_zh_en.onnx \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx \
  53cab20ba8f2eb2f6e2d89ecc18e88ef3222169b61b4419cbc13666744a4574b
echo "models ready in third_party/wake and third_party/voice"
