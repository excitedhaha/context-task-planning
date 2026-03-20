#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "${1:-}")

if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No active task found."
    exit 0
fi

STATE_FILE="$PLAN_DIR/state.json"
if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR"
    exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to read $STATE_FILE"
    exit 0
fi

"$PYTHON_BIN" - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
state = json.loads(state_path.read_text(encoding="utf-8"))
phases = state.get("phases", [])
complete = sum(1 for phase in phases if phase.get("status") == "complete")
blocked = [phase["id"] for phase in phases if phase.get("status") == "blocked"]
active = [phase["id"] for phase in phases if phase.get("status") == "in_progress"]
delegates = state.get("delegation", {}).get("active", [])

print(f"[context-task-planning] Task: {state.get('slug', '(unknown)')}")
print(f"[context-task-planning] Title: {state.get('title', '(unknown)')}")
print(f"[context-task-planning] Status: {state.get('status', '(unknown)')} | Mode: {state.get('mode', '(unknown)')}")
print(f"[context-task-planning] Current phase: {state.get('current_phase', '(unknown)')}")
print(f"[context-task-planning] Phases complete: {complete}/{len(phases)}")
print(f"[context-task-planning] Next action: {state.get('next_action', '')}")

blockers = state.get("blockers", [])
if blockers:
    print("[context-task-planning] Blockers:")
    for blocker in blockers:
        print(f"  - {blocker}")
else:
    print("[context-task-planning] Blockers: none")

if blocked:
    print(f"[context-task-planning] Blocked phases: {', '.join(blocked)}")
if active:
    print(f"[context-task-planning] In-progress phases: {', '.join(active)}")
if delegates:
    print(f"[context-task-planning] Active delegates: {', '.join(delegates)}")
else:
    print("[context-task-planning] Active delegates: none")

if state.get("status") == "done" and complete == len(phases):
    print("[context-task-planning] Task is complete.")
PY

exit 0
