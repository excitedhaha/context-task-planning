#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
ACTIVE_FILE="$PLAN_ROOT/.active_task"

ALLOW_DIRTY=0
AUTO_STASH=0
TASK_ARG=""
STEAL=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --stash)
            AUTO_STASH=1
            ;;
        --allow-dirty)
            ALLOW_DIRTY=1
            ;;
        --steal)
            STEAL=1
            ;;
        -h|--help)
            echo "Usage: $0 [--stash] [--allow-dirty] [--steal] [task-slug]" >&2
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Usage: $0 [--stash] [--allow-dirty] [--steal] [task-slug]" >&2
            exit 1
            ;;
        *)
            if [ -n "$TASK_ARG" ]; then
                echo "Usage: $0 [--stash] [--allow-dirty] [--steal] [task-slug]" >&2
                exit 1
            fi
            TASK_ARG="$1"
            ;;
    esac
    shift
done

if [ "$#" -gt 0 ]; then
    echo "Usage: $0 [--stash] [--allow-dirty] [--steal] [task-slug]" >&2
    exit 1
fi

PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_ARG")

if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to resume." >&2
    exit 1
fi

STATE_FILE="$PLAN_DIR/state.json"
PROGRESS_FILE="$PLAN_DIR/progress.md"
TASK_PLAN_FILE="$PLAN_DIR/task_plan.md"
TASK_SLUG=$(basename "$PLAN_DIR")

if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to resume tasks." >&2
    exit 1
fi

TARGET_STATUS=$("$PYTHON_BIN" - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
state = json.loads(state_path.read_text(encoding="utf-8"))
print(state.get("status", ""))
PY
)

if [ "$TARGET_STATUS" = "archived" ]; then
    echo "Cannot resume an archived task." >&2
    exit 1
fi

if [ "$TARGET_STATUS" = "done" ]; then
    echo "Cannot resume a done task. Reopen it explicitly if you want to continue work." >&2
    exit 1
fi

if [ "$ALLOW_DIRTY" -eq 1 ] && [ "$AUTO_STASH" -eq 1 ]; then
    echo "Choose only one of --stash or --allow-dirty." >&2
    exit 1
fi

if [ "$AUTO_STASH" -eq 1 ]; then
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --target-task "$TASK_SLUG" --stash
elif [ "$ALLOW_DIRTY" -eq 1 ]; then
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --target-task "$TASK_SLUG" --allow-dirty
else
    sh "$SCRIPT_DIR/ensure-switch-safety.sh" --cwd "$WORKSPACE_ROOT" --target-task "$TASK_SLUG"
fi

"$PYTHON_BIN" - "$STATE_FILE" "$PROGRESS_FILE" "$TASK_PLAN_FILE" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
progress_path = Path(sys.argv[2])
task_plan_path = Path(sys.argv[3])

timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
state = json.loads(state_path.read_text(encoding="utf-8"))

if state.get("status") == "archived":
    raise SystemExit("Cannot resume an archived task.")
if state.get("status") == "done":
    raise SystemExit("Cannot resume a done task. Reopen it explicitly if you want to continue work.")

state["status"] = "active"
state["latest_checkpoint"] = f"Task resumed at {timestamp}."
state["updated_at"] = timestamp
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

if progress_path.exists():
    with progress_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(f"### Resume: {timestamp}\n\n")
        fh.write("- Status: active\n")
        fh.write("- Notes:\n")
        fh.write("  - Task resumed via resume-task.sh\n")

if task_plan_path.exists():
    lines = task_plan_path.read_text(encoding="utf-8").splitlines()
    updated = []
    status_written = False
    for line in lines:
        if line.startswith("- Task Slug:"):
            updated.append(line)
            continue
        if line.startswith("- Task Status:"):
            updated.append("- Task Status: `active`")
            status_written = True
        else:
            updated.append(line)
    if not status_written:
        for idx, line in enumerate(updated):
            if line.startswith("- Task Slug:"):
                updated.insert(idx + 1, "- Task Status: `active`")
                break
    task_plan_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY

mkdir -p "$PLAN_ROOT"

if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    if [ "$STEAL" -eq 1 ]; then
        "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --role writer --steal
    else
        "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --role writer
    fi
else
    if [ "$STEAL" -eq 1 ]; then
        "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --role writer --fallback --steal
    else
        "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" bind-session-task --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --role writer --fallback
    fi
    printf '%s\n' "$TASK_SLUG" > "$ACTIVE_FILE"
fi

echo "[context-task-planning] Resumed task: $TASK_SLUG"
echo "[context-task-planning] Task directory: $PLAN_DIR"
if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    echo "[context-task-planning] Session writer binding: ${PLAN_SESSION_KEY} -> $TASK_SLUG"
else
    echo "[context-task-planning] Workspace fallback writer task: $TASK_SLUG"
fi
