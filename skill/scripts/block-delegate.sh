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
    echo "[context-task-planning] No task found to block delegate in." >&2
    exit 1
fi

STATE_FILE="$PLAN_DIR/state.json"
PROGRESS_FILE="$PLAN_DIR/progress.md"
DELEGATE_DIR="$PLAN_DIR/delegates/$DELEGATE_ID"
DELEGATE_STATUS_FILE="$DELEGATE_DIR/status.json"

if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR" >&2
    exit 1
fi

if [ ! -f "$DELEGATE_STATUS_FILE" ]; then
    echo "[context-task-planning] Delegate not found: $DELEGATE_DIR" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to block delegates." >&2
    exit 1
fi

export STATE_FILE PROGRESS_FILE DELEGATE_STATUS_FILE DELEGATE_ID DELEGATE_SUMMARY
"$PYTHON_BIN" <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(os.environ["STATE_FILE"])
progress_path = Path(os.environ["PROGRESS_FILE"])
delegate_status_path = Path(os.environ["DELEGATE_STATUS_FILE"])
delegate_id = os.environ["DELEGATE_ID"]
delegate_summary = os.environ["DELEGATE_SUMMARY"].strip()

timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
state = json.loads(state_path.read_text(encoding="utf-8"))
delegate_state = json.loads(delegate_status_path.read_text(encoding="utf-8"))

if state.get("status") in {"done", "archived"}:
    raise SystemExit("Cannot block a delegate for a done or archived task.")

existing_status = delegate_state.get("status")
if existing_status == "cancelled":
    raise SystemExit("Cannot block a cancelled delegate.")
if existing_status == "complete":
    raise SystemExit("Cannot block a completed delegate.")

if not delegate_summary:
    delegate_summary = delegate_state.get("summary", "").strip() or "Delegate is blocked pending more input or resolution."

delegate_state["status"] = "blocked"
delegate_state["summary"] = delegate_summary
delegate_state["updated_at"] = timestamp
delegate_status_path.write_text(json.dumps(delegate_state, indent=2) + "\n", encoding="utf-8")

active = state.setdefault("delegation", {}).setdefault("active", [])
if delegate_id not in active:
    active.append(delegate_id)
state["latest_checkpoint"] = f"Delegate {delegate_id} blocked at {timestamp}."
state["updated_at"] = timestamp
state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

if progress_path.exists():
    with progress_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(f"### Delegate Blocked: {timestamp}\n\n")
        fh.write(f"- Delegate: `{delegate_id}`\n")
        fh.write("- Status: blocked\n")
        fh.write(f"- Summary: {delegate_summary}\n")
        fh.write("- Notes:\n")
        fh.write("  - Delegate blocked via block-delegate.sh\n")
PY

echo "[context-task-planning] Blocked delegate: $DELEGATE_ID"
echo "[context-task-planning] Delegate directory: $DELEGATE_DIR"
echo "[context-task-planning] Use start-delegate.sh or resume-delegate.sh to continue this lane when work can resume."
