#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${MCP_PYTHON:-.venv/bin/python}"
if "$PYTHON" -c 'import pip' 2>/dev/null; then
    "$PYTHON" -m pip check
elif command -v uv >/dev/null; then
    uv pip check --python "$PYTHON"
else
    echo 'Install pip in the environment or install uv to check dependencies.' >&2
    exit 1
fi
"$PYTHON" -m pytest tests/ -q "$@"
