#!/bin/sh

set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <task-slug>" >&2
    exit 1
fi

TASK_SLUG="$1"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
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
printf '%s\n' "$TASK_SLUG" > "$PLAN_ROOT/.active_task"

echo "Active task set to: $TASK_SLUG"
echo "Workspace root: $WORKSPACE_ROOT"
echo "Task directory: $PLAN_DIR"
