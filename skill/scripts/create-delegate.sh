#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TEMPLATE_DIR="$SKILL_ROOT/templates"

TASK_SLUG=""
DELEGATE_ID=""
DELEGATE_TITLE=""
DELEGATE_KIND="discovery"
DELEGATE_GOAL="[bounded question or task]"
DELEGATE_DELIVERABLE="[what the coordinator needs back]"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --task)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --task" >&2; exit 1; }
            TASK_SLUG="$1"
            ;;
        --id)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --id" >&2; exit 1; }
            DELEGATE_ID="$1"
            ;;
        --title)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --title" >&2; exit 1; }
            DELEGATE_TITLE="$1"
            ;;
        --kind)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --kind" >&2; exit 1; }
            DELEGATE_KIND="$1"
            ;;
        --goal)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --goal" >&2; exit 1; }
            DELEGATE_GOAL="$1"
            ;;
        --deliverable)
            shift
            [ "$#" -gt 0 ] || { echo "Missing value for --deliverable" >&2; exit 1; }
            DELEGATE_DELIVERABLE="$1"
            ;;
        -h|--help)
            echo "Usage: $0 [--task slug] [--id delegate-id] [--title \"Delegate Title\"] [--kind discovery|spike|verify|review|catchup|other] [--goal \"goal\"] [--deliverable \"deliverable\"] [delegate title]" >&2
            exit 0
            ;;
        *)
            if [ -z "$DELEGATE_TITLE" ]; then
                DELEGATE_TITLE="$1"
            else
                DELEGATE_TITLE="$DELEGATE_TITLE $1"
            fi
            ;;
    esac
    shift
done

if [ -z "$DELEGATE_TITLE" ] && [ -z "$DELEGATE_ID" ]; then
    echo "Usage: $0 [--task slug] [--id delegate-id] [--title \"Delegate Title\"] [--kind discovery|spike|verify|review|catchup|other] [--goal \"goal\"] [--deliverable \"deliverable\"] [delegate title]" >&2
    exit 1
fi

if [ -z "$DELEGATE_ID" ]; then
    DELEGATE_ID=$(sh "$SCRIPT_DIR/slugify.sh" "$DELEGATE_TITLE")
else
    DELEGATE_ID=$(sh "$SCRIPT_DIR/slugify.sh" "$DELEGATE_ID")
fi

if [ -z "$DELEGATE_TITLE" ]; then
    DELEGATE_TITLE="$DELEGATE_ID"
fi

PLAN_DIR=$(sh "$SCRIPT_DIR/resolve-plan-dir.sh" "$TASK_SLUG")
if [ -z "$PLAN_DIR" ] || [ ! -d "$PLAN_DIR" ]; then
    echo "[context-task-planning] No task found to attach delegate to." >&2
    exit 1
fi

STATE_FILE="$PLAN_DIR/state.json"
PROGRESS_FILE="$PLAN_DIR/progress.md"
DELEGATES_DIR="$PLAN_DIR/delegates"
DELEGATE_DIR="$DELEGATES_DIR/$DELEGATE_ID"
TASK_NAME=$(basename "$PLAN_DIR")

if [ ! -f "$STATE_FILE" ]; then
    echo "[context-task-planning] Missing state.json in $PLAN_DIR" >&2
    exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "Python is required to create delegates." >&2
    exit 1
fi

ALLOW_MAIN_PLAN_WRITES=1
if [ -n "${PLAN_SESSION_KEY:-}" ]; then
    if ! "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" check-task-access --cwd "$PLAN_DIR" --task "$TASK_NAME" >/dev/null 2>&1; then
        ALLOW_MAIN_PLAN_WRITES=0
    fi
elif ! "$PYTHON_BIN" "$SCRIPT_DIR/task_guard.py" check-task-access --cwd "$PLAN_DIR" --task "$TASK_NAME" --fallback >/dev/null 2>&1; then
    ALLOW_MAIN_PLAN_WRITES=0
fi

export PLAN_DIR STATE_FILE PROGRESS_FILE TEMPLATE_DIR DELEGATE_DIR DELEGATE_ID DELEGATE_TITLE DELEGATE_KIND DELEGATE_GOAL DELEGATE_DELIVERABLE ALLOW_MAIN_PLAN_WRITES
"$PYTHON_BIN" <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

plan_dir = Path(os.environ["PLAN_DIR"])
state_path = Path(os.environ["STATE_FILE"])
progress_path = Path(os.environ["PROGRESS_FILE"])
template_dir = Path(os.environ["TEMPLATE_DIR"])
delegate_dir = Path(os.environ["DELEGATE_DIR"])
delegate_id = os.environ["DELEGATE_ID"]
delegate_title = os.environ["DELEGATE_TITLE"]
delegate_kind = os.environ["DELEGATE_KIND"]
delegate_goal = os.environ["DELEGATE_GOAL"]
delegate_deliverable = os.environ["DELEGATE_DELIVERABLE"]
allow_main_plan_writes = os.environ.get("ALLOW_MAIN_PLAN_WRITES", "1") == "1"

allowed_kinds = {"discovery", "spike", "verify", "review", "catchup", "other"}
if delegate_kind not in allowed_kinds:
    raise SystemExit(f"Unsupported delegate kind: {delegate_kind}")

timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
state = json.loads(state_path.read_text(encoding="utf-8"))

if state.get("status") in {"done", "archived"}:
    raise SystemExit("Cannot create a delegate for a done or archived task.")

task_slug = state.get("slug", plan_dir.name)
planning_path = Path(state.get("planning_path", f".planning/{task_slug}"))
delegate_rel_dir = planning_path / "delegates" / delegate_id
brief_path = delegate_rel_dir / "brief.md"
result_path = delegate_rel_dir / "result.md"
status_path = delegate_dir / "status.json"

delegate_dir.mkdir(parents=True, exist_ok=True)

replacements = {
    "{{TASK_SLUG}}": task_slug,
    "{{DELEGATE_ID}}": delegate_id,
    "{{DELEGATE_TITLE}}": delegate_title,
    "{{DELEGATE_KIND}}": delegate_kind,
    "{{DELEGATE_GOAL}}": delegate_goal,
    "{{DELEGATE_DELIVERABLE}}": delegate_deliverable,
}

for template_name, target_name in (("delegate_brief.md", "brief.md"), ("delegate_result.md", "result.md")):
    target = delegate_dir / target_name
    if target.exists():
        continue
    content = (template_dir / template_name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(key, value)
    target.write_text(content, encoding="utf-8")

created = not status_path.exists()
log_status = "pending"
log_note = "Delegate lane created via create-delegate.sh"
if created:
    delegate_state = {
        "schema_version": "1.0.0",
        "task_slug": task_slug,
        "delegate_id": delegate_id,
        "title": delegate_title,
        "kind": delegate_kind,
        "status": "pending",
        "brief_path": str(brief_path),
        "result_path": str(result_path),
        "summary": "",
        "files_touched": [],
        "promoted_findings": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
else:
    delegate_state = json.loads(status_path.read_text(encoding="utf-8"))
    existing_status = delegate_state.get("status")
    if existing_status == "complete":
        raise SystemExit("Delegate already completed. Use a new delegate id for new work.")
    if existing_status == "cancelled":
        raise SystemExit("Delegate already cancelled. Use a new delegate id for new work.")
    if existing_status == "blocked":
        delegate_state["status"] = "pending"
        delegate_state["updated_at"] = timestamp
        log_note = "Blocked delegate lane reopened via create-delegate.sh"
        log_status = "pending"
    else:
        log_note = "Delegate lane reused via create-delegate.sh"
        log_status = delegate_state.get("status", "pending")

status_path.write_text(json.dumps(delegate_state, indent=2) + "\n", encoding="utf-8")
if allow_main_plan_writes:
    if delegate_state.get("status") not in {"complete", "cancelled"}:
        active = state.setdefault("delegation", {}).setdefault("active", [])
        if delegate_id not in active:
            active.append(delegate_id)

    state.setdefault("delegation", {}).setdefault("enabled", True)
    state.setdefault("delegation", {}).setdefault("single_writer", True)
    state["latest_checkpoint"] = f"Delegate {delegate_id} {'created' if created else 'reused'} at {timestamp}."
    state["updated_at"] = timestamp
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

if allow_main_plan_writes and progress_path.exists():
    with progress_path.open("a", encoding="utf-8") as fh:
        fh.write("\n")
        fh.write(f"### Delegate {'Created' if created else 'Updated'}: {timestamp}\n\n")
        fh.write(f"- Delegate: `{delegate_id}`\n")
        fh.write(f"- Kind: `{delegate_kind}`\n")
        fh.write(f"- Status: {log_status}\n")
        fh.write("- Notes:\n")
        fh.write(f"  - {log_note}\n")
        fh.write(f"  - Brief: `{brief_path}`\n")
        fh.write(f"  - Result: `{result_path}`\n")
PY

echo "[context-task-planning] Delegate ready: $DELEGATE_ID"
echo "[context-task-planning] Task directory: $PLAN_DIR"
echo "[context-task-planning] Delegate directory: $DELEGATE_DIR"
if [ "$ALLOW_MAIN_PLAN_WRITES" -eq 0 ]; then
    echo "[context-task-planning] Observe-only session: main planning files were left unchanged; only the delegate lane was updated."
fi
echo "[context-task-planning] Fill brief.md, run start-delegate.sh when work begins, let the subagent work only inside this lane, then run complete-delegate.sh and promote-delegate.sh."
