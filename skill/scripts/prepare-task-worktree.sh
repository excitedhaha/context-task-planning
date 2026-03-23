#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PYTHON_BIN="$(command -v python3 || command -v python || true)"

if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to prepare task worktrees." >&2
    exit 1
fi

TASK_SLUG=""
REPO_ID=""
BASE_REF=""
BRANCH_NAME=""
CUSTOM_PATH=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        --repo)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --repo" >&2; exit 1; }
            REPO_ID="$1"
            ;;
        --base)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --base" >&2; exit 1; }
            BASE_REF="$1"
            ;;
        --branch)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --branch" >&2; exit 1; }
            BRANCH_NAME="$1"
            ;;
        --path)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --path" >&2; exit 1; }
            CUSTOM_PATH="$1"
            ;;
        -h|--help)
            echo "Usage: $0 --task slug --repo repo-id [--base ref] [--branch branch] [--path relative-path]" >&2
            exit 0
            ;;
        *)
            echo "Unexpected argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

if [ -z "$TASK_SLUG" ] || [ -z "$REPO_ID" ]; then
    echo "Usage: $0 --task slug --repo repo-id [--base ref] [--branch branch] [--path relative-path]" >&2
    exit 1
fi

BINDING_JSON=$("$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" task-repo-binding --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --repo "$REPO_ID" --json)

eval "$($PYTHON_BIN - "$BINDING_JSON" <<'PY'
import json
import shlex
import sys

payload = json.loads(sys.argv[1])
binding = payload["binding"]

for key in ("repo_id", "repo_path", "checkout_path", "mode", "branch"):
    value = str(binding.get(key) or "")
    print(f"{key.upper()}={shlex.quote(value)}")
PY
)"

REPO_ABS="$WORKSPACE_ROOT/$REPO_PATH"

if [ -z "$BRANCH_NAME" ]; then
    BRANCH_NAME="task/$TASK_SLUG"
fi

if [ -z "$BASE_REF" ]; then
    BASE_REF=$(git -C "$REPO_ABS" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
fi

if [ -z "$BASE_REF" ] || [ "$BASE_REF" = "HEAD" ]; then
    BASE_REF="HEAD"
fi

if [ -z "$CUSTOM_PATH" ]; then
    CUSTOM_PATH="$WORKSPACE_ROOT/.worktrees/$TASK_SLUG/$REPO_ID"
fi

CHECKOUT_REL=$($PYTHON_BIN - "$WORKSPACE_ROOT" "$CUSTOM_PATH" <<'PY'
import sys
from pathlib import Path

workspace = Path(sys.argv[1]).resolve()
candidate = Path(sys.argv[2]).expanduser()
if not candidate.is_absolute():
    candidate = workspace / candidate
candidate = candidate.resolve()
print(candidate.relative_to(workspace))
PY
)

CHECKOUT_ABS="$WORKSPACE_ROOT/$CHECKOUT_REL"

if git -C "$CHECKOUT_ABS" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    EXISTING_BRANCH=$(git -C "$CHECKOUT_ABS" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" set-task-repo-binding --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --repo "$REPO_ID" --mode worktree --checkout-path "$CHECKOUT_REL" --branch "$EXISTING_BRANCH" --base-branch "$BASE_REF" >/dev/null
    echo "[context-task-planning] Reused existing worktree for task: $TASK_SLUG"
    echo "[context-task-planning] Repo: $REPO_ID"
    echo "[context-task-planning] Checkout path: $CHECKOUT_REL"
    exit 0
fi

mkdir -p "$(dirname "$CHECKOUT_ABS")"

if git -C "$REPO_ABS" show-ref --verify --quiet "refs/heads/$BRANCH_NAME"; then
    git -C "$REPO_ABS" worktree add "$CHECKOUT_ABS" "$BRANCH_NAME"
else
    git -C "$REPO_ABS" worktree add -b "$BRANCH_NAME" "$CHECKOUT_ABS" "$BASE_REF"
fi

FINAL_BRANCH=$(git -C "$CHECKOUT_ABS" rev-parse --abbrev-ref HEAD 2>/dev/null || true)
"$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" set-task-repo-binding --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --repo "$REPO_ID" --mode worktree --checkout-path "$CHECKOUT_REL" --branch "$FINAL_BRANCH" --base-branch "$BASE_REF" >/dev/null

echo "[context-task-planning] Prepared worktree for task: $TASK_SLUG"
echo "[context-task-planning] Repo: $REPO_ID"
echo "[context-task-planning] Branch: ${FINAL_BRANCH:-$BRANCH_NAME}"
echo "[context-task-planning] Checkout path: $CHECKOUT_REL"
