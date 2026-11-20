#!/usr/bin/env bash
# Download the Agora IoT (RTSA Lite) SDK for aarch64 Linux into third_party/.
# The SDK is ~21 MB and is not committed to git.
set -euo pipefail
cd "$(dirname "$0")/.."
URL="https://download.agora.io/rtsasdk/release/Agora-RTSALite-RmRdRcAcAjCF-aarch64-linux-gnu-v1.9.7-20251127_103054-992914.tgz"
DEST=third_party/agora_rtsa_sdk
if [ -f "$DEST/agora_sdk/include/agora_rtc_api.h" ]; then
  echo "SDK already present in $DEST"; exit 0
fi
mkdir -p third_party
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "Downloading Agora IoT SDK v1.9.7 (aarch64-linux-gnu)..."
curl -fL --progress-bar -o "$tmp/sdk.tgz" "$URL"
tar xzf "$tmp/sdk.tgz" -C "$tmp"
rm -rf "$DEST"
mv "$tmp/agora_rtsa_sdk" "$DEST"
echo "SDK ready in $DEST"
