#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOICE_SCRIPT="${REPO_DIR}/voice.py"

if [ -x "${REPO_DIR}/.venv/bin/python" ]; then
    VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    VENV_PYTHON="python3"
else
    echo "Error: Python 3 runtime not found." >&2
    exit 1
fi

exec "${VENV_PYTHON}" "${VOICE_SCRIPT}" --verify "$@"
