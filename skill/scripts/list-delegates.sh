#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

TASK_SLUG=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug]" >&2
            exit 0
            ;;
        *)
            echo "Unexpected argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_SLUG")
if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to list delegates for."
    exit 0
fi

STATE_FILE="$PLAN_DIR/state.json"
DELEGATES_DIR="$PLAN_DIR/delegates"

if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR"
    exit 0
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[context-task-planning] Python is required to list delegates."
    exit 0
fi

"$PYTHON_BIN" - "$STATE_FILE" "$DELEGATES_DIR" <<'PY'
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
delegates_dir = Path(sys.argv[2])
state = json.loads(state_path.read_text(encoding="utf-8"))
active = set(state.get("delegation", {}).get("active", []))

status_order = {
    "running": 0,
    "pending": 1,
    "blocked": 2,
    "complete": 3,
    "cancelled": 4,
}

rows = []
if delegates_dir.is_dir():
    for entry in delegates_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith('.'):
            continue
        status_file = entry / "status.json"
        if not status_file.exists():
            continue
        try:
            dstate = json.loads(status_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        delegate_id = dstate.get("delegate_id", entry.name)
        summary = (dstate.get("summary") or "").strip() or "-"
        rows.append(
            {
                "mark": "active" if delegate_id in active else "-",
                "delegate_id": delegate_id,
                "kind": dstate.get("kind", "-"),
                "status": dstate.get("status", "unknown"),
                "promoted": str(len(dstate.get("promoted_findings", []))),
                "updated": dstate.get("updated_at", "-"),
                "title": dstate.get("title", "-"),
                "summary": summary,
            }
        )

print(f"[context-task-planning] Task: {state.get('slug', '(unknown)')}")
print(f"[context-task-planning] Title: {state.get('title', '(unknown)')}")
print(f"[context-task-planning] Delegate root: {delegates_dir}")

if not rows:
    print("[context-task-planning] No delegates found.")
    sys.exit(0)

rows.sort(key=lambda row: row["updated"], reverse=True)
rows.sort(key=lambda row: status_order.get(row["status"], 99))
rows.sort(key=lambda row: row["mark"] != "active")

print("")
headers = ["MARK", "ID", "KIND", "STATUS", "PROMOTED", "UPDATED", "TITLE", "SUMMARY"]
widths = [
    max(len(headers[0]), *(len(row["mark"]) for row in rows)),
    max(len(headers[1]), *(len(row["delegate_id"]) for row in rows)),
    max(len(headers[2]), *(len(row["kind"]) for row in rows)),
    max(len(headers[3]), *(len(row["status"]) for row in rows)),
    max(len(headers[4]), *(len(row["promoted"]) for row in rows)),
    max(len(headers[5]), *(len(row["updated"]) for row in rows)),
    max(len(headers[6]), *(len(row["title"]) for row in rows)),
    max(len(headers[7]), *(len(row["summary"]) for row in rows)),
]
fmt = "  ".join(f"{{:{width}}}" for width in widths)
print(fmt.format(*headers))
print(fmt.format(*["-" * width for width in widths]))
for row in rows:
    print(
        fmt.format(
            row["mark"],
            row["delegate_id"],
            row["kind"],
            row["status"],
            row["promoted"],
            row["updated"],
            row["title"],
            row["summary"],
        )
    )
PY
