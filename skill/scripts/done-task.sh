#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORKSPACE_ROOT=$(sh "$SCRIPT_DIR/resolve-workspace-root.sh")
PLAN_ROOT="$WORKSPACE_ROOT/.planning"
PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "${1:-}")

if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to mark done." >&2
    exit 1
fi

STATE_FILE="$PLAN_DIR/state.json"
PROGRESS_FILE="$PLAN_DIR/progress.md"
TASK_PLAN_FILE="$PLAN_DIR/task_plan.md"
ACTIVE_FILE="$PLAN_ROOT/.active_task"
TASK_SLUG=$(basename "$PLAN_DIR")

if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to mark tasks done." >&2
    exit 1
fi

if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" check-task-access --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG"
else
    "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" check-task-access --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG" --fallback
fi

"$PYTHON_BIN" - "$STATE_FILE" "$PROGRESS_FILE" "$TASK_PLAN_FILE" "$PLAN_DIR" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
progress_path = Path(sys.argv[2])
task_plan_path = Path(sys.argv[3])
plan_dir = Path(sys.argv[4])

timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
state = json.loads(state_path.read_text(encoding="utf-8"))

if state.get("status") == "archived":
    raise SystemExit("Cannot mark an archived task done.")

if state.get("blockers"):
    raise SystemExit("Cannot mark task done while blockers are still recorded.")

active_delegates = []
delegates_dir = plan_dir / "delegates"
if delegates_dir.is_dir():
    for entry in delegates_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        status_path = entry / "status.json"
        if not status_path.exists():
            continue
        delegate_state = json.loads(status_path.read_text(encoding="utf-8"))
        if delegate_state.get("status") in {"complete", "cancelled"}:
            continue
        active_delegates.append(delegate_state.get("delegate_id", entry.name))

if active_delegates:
    raise SystemExit("Cannot mark task done while active delegates remain: " + ", ".join(active_delegates))

blocked_phases = [phase.get("id", "(unknown)") for phase in state.get("phases", []) if phase.get("status") == "blocked"]
if blocked_phases:
    raise SystemExit("Cannot mark task done while blocked phases exist: " + ", ".join(blocked_phases))

for phase in state.get("phases", []):
    phase["status"] = "complete"

state["status"] = "done"
state["mode"] = "verify"
state["current_phase"] = "verify"
state["next_action"] = "Done. Archive this task when you no longer need it in active lists."
state["latest_checkpoint"] = f"Task marked done at {timestamp}."
state["updated_at"] = timestamp
state["delegation"]["active"] = []
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

if progress_path.exists():
    with progress_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(f"### Done: {timestamp}\n\n")
        fh.write("- Status: done\n")
        fh.write("- Notes:\n")
        fh.write("  - Task marked done via done-task.sh\n")
        fh.write("  - Archive when you no longer need the task in active lists\n")

if task_plan_path.exists():
    lines = task_plan_path.read_text(encoding="utf-8").splitlines()
    updated = []
    status_written = False
    for line in lines:
        if line.startswith("- Task Slug:"):
            updated.append(line)
            continue
        if line.startswith("- Task Status:"):
            updated.append("- Task Status: `done`")
            status_written = True
        elif line.startswith("- Current Mode:"):
            updated.append("- Current Mode: `verify`")
        elif line.startswith("- Current Phase:"):
            updated.append("- Current Phase: `verify`")
        elif line.startswith("- Next Action:"):
            updated.append("- Next Action: Done. Archive this task when you no longer need it in active lists.")
        else:
            updated.append(line)
    if not status_written:
        for idx, line in enumerate(updated):
            if line.startswith("- Task Slug:"):
                updated.insert(idx + 1, "- Task Status: `done`")
                break
    task_plan_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
PY

if [ -f "$ACTIVE_FILE" ]; then
    ACTIVE_SLUG=$(tr -d '\r\n' < "$ACTIVE_FILE")
    if [ "$ACTIVE_SLUG" = "$TASK_SLUG" ]; then
        rm -f "$ACTIVE_FILE"
        echo "[context-task-planning] Cleared shared active pointer for $TASK_SLUG"
    fi
fi

"$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" clear-task-sessions --cwd "$WORKSPACE_ROOT" --task "$TASK_SLUG"

echo "[context-task-planning] Marked done: $TASK_SLUG"
echo "[context-task-planning] Task directory: $PLAN_DIR"
