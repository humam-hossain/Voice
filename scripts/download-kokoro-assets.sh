#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${ROOT_DIR}/models/kokoro"

mkdir -p "${MODEL_DIR}"

wget -c -O "${MODEL_DIR}/kokoro-v1.0.onnx" \
  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"

wget -c -O "${MODEL_DIR}/voices-v1.0.bin" \
  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

echo "Kokoro assets installed in ${MODEL_DIR}"
