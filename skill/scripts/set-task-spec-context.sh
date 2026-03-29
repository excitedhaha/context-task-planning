#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN="$(command -v python3 || command -v python || true)"

if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to set task spec context." >&2
    exit 1
fi

TASK_SLUG=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug] [--clear] [--provider openspec] [--ref spec-ref] [--artifact ref] [--summary text]" >&2
            exit 0
            ;;
        --provider|--ref|--artifact|--summary|--clear)
            break
            ;;
        *)
            if [ -n "$TASK_SLUG" ]; then
                echo "Unexpected argument: $1" >&2
                exit 1
            fi
            TASK_SLUG="$1"
            ;;
    esac
    shift
done

if [ -z "$TASK_SLUG" ]; then
    echo "Usage: $0 [--task slug] [--clear] [--provider openspec] [--ref spec-ref] [--artifact ref] [--summary text]" >&2
    exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" set-task-spec-context --task "$TASK_SLUG" "$@"
sh "$SCRIPT_DIR/validate-task.sh" --task "$TASK_SLUG" --fix-warnings >/dev/null
