#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

TASK_SLUG=""
DELEGATE_ID=""
DELEGATE_SUMMARY=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        --summary)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --summary" >&2; exit 1; }
            DELEGATE_SUMMARY="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug] [--summary \"summary\"] <delegate-id>" >&2
            exit 0
            ;;
        *)
            if [ -z "$DELEGATE_ID" ]; then
                DELEGATE_ID="$1"
            else
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            ;;
    esac
    shift
done

if [ -z "$DELEGATE_ID" ]; then
    echo "Usage: $0 [--task slug] [--summary \"summary\"] <delegate-id>" >&2
    exit 1
fi

DELEGATE_ID=$(sh "$SCRIPT_DIR/slugify.sh" "$DELEGATE_ID")
PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_SLUG")
if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to resume delegate in." >&2
    exit 1
fi

DELEGATE_STATUS_FILE="$PLAN_DIR/delegates/$DELEGATE_ID/status.json"
if [ ! -f "$DELEGATE_STATUS_FILE" ]; then
    echo "[context-task-planning] Delegate not found: $PLAN_DIR/delegates/$DELEGATE_ID" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to resume delegates." >&2
    exit 1
fi

"$PYTHON_BIN" - "$DELEGATE_STATUS_FILE" <<'PY'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if state.get("status") != "blocked":
    raise SystemExit("resume-delegate.sh expects a blocked delegate. Use start-delegate.sh for pending lanes.")
PY

if [ -n "$TASK_SLUG" ] && [ -n "$DELEGATE_SUMMARY" ]; then
    exec sh "$SCRIPT_DIR/start-delegate.sh" --task "$TASK_SLUG" --summary "$DELEGATE_SUMMARY" "$DELEGATE_ID"
elif [ -n "$TASK_SLUG" ]; then
    exec sh "$SCRIPT_DIR/start-delegate.sh" --task "$TASK_SLUG" "$DELEGATE_ID"
elif [ -n "$DELEGATE_SUMMARY" ]; then
    exec sh "$SCRIPT_DIR/start-delegate.sh" --summary "$DELEGATE_SUMMARY" "$DELEGATE_ID"
else
    exec sh "$SCRIPT_DIR/start-delegate.sh" "$DELEGATE_ID"
fi
