#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN="$(command -v python3 || command -v python || true)"

if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to inspect compact task context."
    exit 0
fi

"$PYTHON_BIN" "$SCRIPT_DIR/compact_context.py" --cwd "$PWD" "$@"
