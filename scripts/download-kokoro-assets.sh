#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="${ROOT_DIR}/models/kokoro"

# Detect Python runtime
if [ -x "${ROOT_DIR}/.venv/bin/python" ]; then
    VENV_PYTHON="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    VENV_PYTHON="python3"
else
    VENV_PYTHON=""
fi

if [ -n "${VENV_PYTHON}" ]; then
    exec "${VENV_PYTHON}" "${ROOT_DIR}/voice.py" --download-tts-assets "$@"
fi

# Fallback if Python is unavailable
mkdir -p "${MODEL_DIR}"
echo "Python runtime unavailable; falling back to direct binary retrieval..."

MODEL_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

if command -v curl >/dev/null 2>&1; then
    curl -L -C - -o "${MODEL_DIR}/kokoro-v1.0.onnx.tmp" "${MODEL_URL}"
    curl -L -C - -o "${MODEL_DIR}/voices-v1.0.bin.tmp" "${VOICES_URL}"
elif command -v wget >/dev/null 2>&1; then
    wget -c -O "${MODEL_DIR}/kokoro-v1.0.onnx.tmp" "${MODEL_URL}"
    wget -c -O "${MODEL_DIR}/voices-v1.0.bin.tmp" "${VOICES_URL}"
else
    echo "Error: neither curl, wget, nor python is available." >&2
    exit 1
fi

# Basic size verification before atomic replace
MODEL_SIZE=$(wc -c < "${MODEL_DIR}/kokoro-v1.0.onnx.tmp" | tr -d ' ')
VOICES_SIZE=$(wc -c < "${MODEL_DIR}/voices-v1.0.bin.tmp" | tr -d ' ')

if [ "${MODEL_SIZE}" -lt 300000000 ]; then
    echo "Error: downloaded kokoro-v1.0.onnx is undersized (${MODEL_SIZE} bytes < 300000000 bytes)." >&2
    rm -f "${MODEL_DIR}/kokoro-v1.0.onnx.tmp"
    exit 1
fi

if [ "${VOICES_SIZE}" -lt 20000000 ]; then
    echo "Error: downloaded voices-v1.0.bin is undersized (${VOICES_SIZE} bytes < 20000000 bytes)." >&2
    rm -f "${MODEL_DIR}/voices-v1.0.bin.tmp"
    exit 1
fi

mv "${MODEL_DIR}/kokoro-v1.0.onnx.tmp" "${MODEL_DIR}/kokoro-v1.0.onnx"
mv "${MODEL_DIR}/voices-v1.0.bin.tmp" "${MODEL_DIR}/voices-v1.0.bin"

echo "Kokoro assets installed and verified in ${MODEL_DIR}"
