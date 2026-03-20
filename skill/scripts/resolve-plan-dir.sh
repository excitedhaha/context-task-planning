#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
REQUESTED_SLUG="${1:-}"

is_status_dir() {
    dir="$1"
    wanted="$2"
    state_file="$dir/state.json"

    if [ -f "$state_file" ] && grep -Eq '"status"[[:space:]]*:[[:space:]]*"'"$wanted"'"' "$state_file"; then
        return 0
    fi

    return 1
}

is_auto_selectable_dir() {
    dir="$1"

    if is_status_dir "$dir" archived || is_status_dir "$dir" paused || is_status_dir "$dir" done; then
        return 1
    fi

    return 0
}

resolve_slug() {
    slug="$1"
    allow_archived="${2:-yes}"

    if [ -z "$slug" ]; then
        return 1
    fi

    candidate="$PLAN_ROOT/$slug"
    if [ -d "$candidate" ]; then
        if [ "$allow_archived" = "no" ] && is_status_dir "$candidate" archived; then
            return 1
        fi
        printf '%s\n' "$candidate"
        return 0
    fi

    return 1
}

if [ -n "$REQUESTED_SLUG" ] && resolve_slug "$REQUESTED_SLUG" yes; then
    exit 0
fi

if [ -n "${PLAN_TASK:-}" ] && resolve_slug "$PLAN_TASK" yes; then
    exit 0
fi

if [ -f "$PLAN_ROOT/.active_task" ]; then
    active_slug=$(tr -d '\r\n' < "$PLAN_ROOT/.active_task")
    if resolve_slug "$active_slug" no; then
        exit 0
    fi
fi

latest=""
if [ -d "$PLAN_ROOT" ]; then
    for dir in "$PLAN_ROOT"/*; do
        if [ -d "$dir" ]; then
            if ! is_auto_selectable_dir "$dir"; then
                continue
            fi
            if [ -z "$latest" ] || [ "$dir" -nt "$latest" ]; then
                latest="$dir"
            fi
        fi
    done
fi

if [ -n "$latest" ]; then
    printf '%s\n' "$latest"
fi
