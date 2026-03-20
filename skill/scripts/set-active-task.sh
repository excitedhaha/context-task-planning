#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
ACTIVE_FILE="$PLAN_ROOT/.active_task"

ALLOW_DIRTY=0
AUTO_STASH=0
TASK_SLUG=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --stash)
            AUTO_STASH=1
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            ;;
        -h|--help)
            echo "Usage: $0 [--stash] [--allow-dirty] <task-slug>" >&2
            exit 0
            ;;
        -*)
            echo "Usage: $0 [--stash] [--allow-dirty] <task-slug>" >&2
            exit 1
            ;;
        *)
            if [ -n "$TASK_SLUG" ]; then
                echo "Usage: $0 [--stash] [--allow-dirty] <task-slug>" >&2
                exit 1
            fi
            TASK_SLUG="$1"
            ;;
    esac
    shift
done

if [ -z "$TASK_SLUG" ]; then
    echo "Usage: $0 [--stash] [--allow-dirty] <task-slug>" >&2
    exit 1
fi

if [ "$ALLOW_DIRTY" -eq 1 ] && [ "$AUTO_STASH" -eq 1 ]; then
    echo "Choose only one of --stash or --allow-dirty." >&2
    exit 1
fi

PLAN_DIR="$PLAN_ROOT/$TASK_SLUG"

if [ ! -d "$PLAN_DIR" ]; then
    echo "Task not found: $PLAN_DIR" >&2
    exit 1
fi

if [ -f "$PLAN_DIR/state.json" ] && grep -Eq '"status"[[:space:]]*:[[:space:]]*"archived"' "$PLAN_DIR/state.json"; then
    echo "Cannot activate archived task: $TASK_SLUG" >&2
    exit 1
fi

mkdir -p "$PLAN_ROOT"

CURRENT_ACTIVE_SLUG=""
if [ -f "$ACTIVE_FILE" ]; then
    CURRENT_ACTIVE_SLUG=$(tr -d '\r\n' < "$ACTIVE_FILE")
fi

if [ "$AUTO_STASH" -eq 1 ]; then
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --source-task "$CURRENT_ACTIVE_SLUG" --target-task "$TASK_SLUG" --stash
elif [ "$ALLOW_DIRTY" -eq 1 ]; then
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --source-task "$CURRENT_ACTIVE_SLUG" --target-task "$TASK_SLUG" --allow-dirty
else
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --source-task "$CURRENT_ACTIVE_SLUG" --target-task "$TASK_SLUG"
fi

printf '%s\n' "$TASK_SLUG" > "$ACTIVE_FILE"

echo "Active task set to: $TASK_SLUG"
echo "Workspace root: $WORKSPACE_ROOT"
echo "Task directory: $PLAN_DIR"
